"""Import service: turns a path or URL into stored, analysable commit data."""
from __future__ import annotations

import hashlib
import os
import re
import shutil

from . import git_parser
from .git_parser import GitError
from .store import Store

URL_PATTERN = re.compile(r"^(https?://|ssh://|git://|git@[\w.-]+:)", re.IGNORECASE)
# Never let git ask for a username/password in the terminal: fail fast instead.
NO_PROMPT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}


class ImportError_(Exception):
    """Raised for anything the user can fix: bad path, bad URL, clone failure."""


def is_url(source: str) -> bool:
    return bool(URL_PATTERN.match(source))


def name_from_url(url: str) -> str:
    tail = re.split(r"[/:]", url.rstrip("/"))[-1]
    return tail[:-4] if tail.endswith(".git") else tail or "repository"


class Importer:
    def __init__(self, store: Store, clone_dir: str):
        self.store = store
        self.clone_dir = clone_dir

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def import_source(self, source: str) -> dict:
        """Import a repository. Importing the same source again refreshes it.

        Returns ``{"repository": {...}, "new_commits": int, "created": bool}``.
        """
        source = (source or "").strip()
        if not source:
            raise ImportError_("Please enter a local folder path or a Git URL.")
        if source.startswith("-"):
            raise ImportError_("Source cannot start with '-'.")

        if is_url(source):
            source = source.rstrip("/")
            existing = self.store.find_repository_by_source(source)
            if existing:
                return {**self.refresh(existing["id"]), "created": False}
            path = self._clone(source)
            name = name_from_url(source)
        else:
            path = self._resolve_local(source)
            source = path
            existing = self.store.find_repository_by_source(source)
            if existing:
                return {**self.refresh(existing["id"]), "created": False}
            name = os.path.basename(path) or path

        head = git_parser.head_sha(path)
        commits = self._read(path)
        repo_id = self.store.create_repository(name, source, path, head)
        inserted = self.store.save_commits(repo_id, commits)
        return {"repository": self.store.get_repository(repo_id),
                "new_commits": inserted, "created": True}

    def refresh(self, repo_id: int) -> dict:
        """Pull new commits. Only commits after the last imported HEAD are parsed."""
        repo = self.store.get_repository(repo_id)
        if repo is None:
            raise ImportError_("Repository not found.")
        path = repo["path"]
        if not git_parser.is_git_repo(path):
            if is_url(repo["source"]):
                path = self._clone(repo["source"])
            else:
                raise ImportError_(f"Folder no longer exists or is not a Git repository: {path}")
        elif is_url(repo["source"]):
            self._pull(path)

        old_head, new_head = repo["head_sha"], git_parser.head_sha(path)
        if new_head == old_head:
            inserted = 0
        elif old_head and new_head and git_parser.is_ancestor(path, old_head, new_head):
            inserted = self.store.save_commits(repo_id, self._read(path, since_sha=old_head))
        else:
            # first import of an empty repo, or history was rewritten: rebuild from scratch
            self.store.clear_commits(repo_id)
            inserted = self.store.save_commits(repo_id, self._read(path))
        self.store.update_head(repo_id, new_head)
        return {"repository": self.store.get_repository(repo_id), "new_commits": inserted}

    def delete(self, repo_id: int) -> bool:
        repo = self.store.get_repository(repo_id)
        if repo is None:
            return False
        self.store.delete_repository(repo_id)
        if self._inside_clone_dir(repo["path"]):
            shutil.rmtree(repo["path"], ignore_errors=True)
        return True

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _read(self, path: str, since_sha: str | None = None):
        try:
            return git_parser.read_commits(path, since_sha=since_sha)
        except GitError as exc:
            raise ImportError_(str(exc)) from exc

    @staticmethod
    def _resolve_local(source: str) -> str:
        path = os.path.abspath(os.path.expanduser(source))
        if not os.path.isdir(path):
            raise ImportError_(f"Folder not found: {path}")
        if not git_parser.is_git_repo(path):
            raise ImportError_(f"Not a Git repository: {path}")
        return os.path.normpath(git_parser.repo_root(path))

    def _clone_path(self, url: str) -> str:
        digest = hashlib.sha1(url.encode()).hexdigest()[:8]
        safe = re.sub(r"[^\w.-]", "_", name_from_url(url))
        return os.path.join(self.clone_dir, f"{safe}-{digest}")

    def _clone(self, url: str) -> str:
        dest = self._clone_path(url)
        if git_parser.is_git_repo(dest):
            self._pull(dest)
            return dest
        if os.path.exists(dest):
            shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(self.clone_dir, exist_ok=True)
        try:
            git_parser.run_git(["clone", "--quiet", "--no-tags", "--", url, dest],
                               timeout=600, env=NO_PROMPT_ENV)
        except GitError as exc:
            shutil.rmtree(dest, ignore_errors=True)
            raise ImportError_(f"Could not clone {url}. Is the URL correct and public? "
                               f"({exc})") from exc
        return dest

    def _pull(self, path: str) -> None:
        try:
            git_parser.run_git(["pull", "--quiet", "--ff-only"], cwd=path, env=NO_PROMPT_ENV)
        except GitError:
            # remote history rewritten: fetch and hard-reset our private clone
            try:
                git_parser.run_git(["fetch", "--quiet", "origin"], cwd=path, env=NO_PROMPT_ENV)
                git_parser.run_git(["reset", "--quiet", "--hard", "@{upstream}"], cwd=path)
            except GitError as exc:
                raise ImportError_(f"Could not update clone: {exc}") from exc

    def _inside_clone_dir(self, path: str) -> bool:
        clone_root = os.path.realpath(self.clone_dir)
        return os.path.realpath(path).startswith(clone_root + os.sep)
