"""Import service: turns a path or URL into stored, analysable commit data."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

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
    """Imports repositories while storing only metadata, never source code.

    * Local folders are read in place; nothing is copied.
    * URLs are read from a temporary *bare* clone (git objects only, no files checked
      out) that is deleted as soon as the commit metadata has been saved.
      This keeps the Deliverable-1 rule "never clone or store source code locally"
      while avoiding one GitHub API call per commit (rate limits).
    """

    def __init__(self, store: Store, clone_dir: str):
        self.store = store
        self.clone_dir = clone_dir  # parent folder for short-lived temporary clones

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
            name = name_from_url(source)
        else:
            source = self._resolve_local(source)
            name = os.path.basename(source) or source

        existing = self.store.find_repository_by_source(source)
        if existing:
            return {**self.refresh(existing["id"]), "created": False}

        with self._open(source) as path:
            head = git_parser.head_sha(path)
            commits = self._read(path)
        repo_id = self.store.create_repository(name, source, source, head)
        inserted = self.store.save_commits(repo_id, commits)
        return {"repository": self.store.get_repository(repo_id),
                "new_commits": inserted, "created": True}

    def refresh(self, repo_id: int) -> dict:
        """Read new commits. Only commits after the last imported HEAD are parsed."""
        repo = self.store.get_repository(repo_id)
        if repo is None:
            raise ImportError_("Repository not found.")
        with self._open(repo["source"]) as path:
            old_head, new_head = repo["head_sha"], git_parser.head_sha(path)
            if new_head == old_head:
                inserted = 0
            elif old_head and new_head and git_parser.is_ancestor(path, old_head, new_head):
                inserted = self.store.save_commits(repo_id, self._read(path, since_sha=old_head))
            else:
                # first import of an empty repo, or history was rewritten: rebuild
                self.store.clear_commits(repo_id)
                inserted = self.store.save_commits(repo_id, self._read(path))
        self.store.update_head(repo_id, new_head)
        return {"repository": self.store.get_repository(repo_id), "new_commits": inserted}

    def delete(self, repo_id: int) -> bool:
        """Remove stored metadata. The user's own folders are never touched."""
        if self.store.get_repository(repo_id) is None:
            return False
        self.store.delete_repository(repo_id)
        return True

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @contextmanager
    def _open(self, source: str) -> Iterator[str]:
        """Yield a path git can read: the folder itself, or a temporary bare clone."""
        if not is_url(source):
            if not git_parser.is_git_repo(source):
                raise ImportError_(f"Folder no longer exists or is not a Git repository: {source}")
            yield source
            return
        os.makedirs(self.clone_dir, exist_ok=True)
        workdir = tempfile.mkdtemp(prefix="dcv-", dir=self.clone_dir)
        target = os.path.join(workdir, "repo.git")
        try:
            try:
                git_parser.run_git(["clone", "--bare", "--quiet", "--no-tags", "--", source, target],
                                   timeout=600, env=NO_PROMPT_ENV)
            except GitError as exc:
                raise ImportError_(f"Could not clone {source}. Is the URL correct and public? "
                                   f"({exc})") from exc
            yield target
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

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
