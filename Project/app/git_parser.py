"""Read commit history from a Git repository using the git CLI.

The parser is split in two so it can be unit-tested without a real repository:
    * ``read_commits`` runs ``git log`` and returns the raw text.
    * ``parse_log`` is a pure function that turns that text into ``Commit`` objects.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime

# ASCII "record separator" starts every commit, "unit separator" splits fields.
RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"
LOG_FORMAT = f"{RECORD_SEP}%H{FIELD_SEP}%aN{FIELD_SEP}%aE{FIELD_SEP}%aI{FIELD_SEP}%P{FIELD_SEP}%s"

_BRACE_RENAME = re.compile(r"\{([^{}]*) => ([^{}]*)\}")


class GitError(Exception):
    """Raised when a git command fails."""


@dataclass
class FileChange:
    path: str
    additions: int
    deletions: int
    is_binary: bool = False


@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: str
    authored_at: datetime
    parents: list[str] = field(default_factory=list)
    message: str = ""
    files: list[FileChange] = field(default_factory=list)

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def deletions(self) -> int:
        return sum(f.deletions for f in self.files)


# --------------------------------------------------------------------------- #
# git command helpers
# --------------------------------------------------------------------------- #
def run_git(args: list[str], cwd: str | None = None, timeout: int = 300,
            env: dict | None = None) -> str:
    """Run ``git <args>`` and return stdout. Never uses a shell."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env={**os.environ, **env} if env else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:  # git not installed
        raise GitError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} timed out") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise GitError(f"git {args[0]} failed: {message}")
    return result.stdout


def is_git_repo(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    try:
        out = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    except GitError:
        return False
    return out.strip() == "true"


def repo_root(path: str) -> str:
    return run_git(["rev-parse", "--show-toplevel"], cwd=path).strip()


def head_sha(path: str) -> str | None:
    """SHA of HEAD, or None for a repository with no commits yet."""
    try:
        return run_git(["rev-parse", "--verify", "HEAD"], cwd=path).strip()
    except GitError:
        return None


def is_ancestor(path: str, older: str, newer: str) -> bool:
    try:
        run_git(["merge-base", "--is-ancestor", older, newer], cwd=path)
        return True
    except GitError:
        return False


def read_commits(path: str, since_sha: str | None = None) -> list[Commit]:
    """Return commits reachable from HEAD (only those after ``since_sha`` if given)."""
    if head_sha(path) is None:
        return []
    args = [
        "-c", "core.quotepath=off",
        "log", "--numstat", "-M", f"--pretty=format:{LOG_FORMAT}",
    ]
    args.append(f"{since_sha}..HEAD" if since_sha else "HEAD")
    return parse_log(run_git(args, cwd=path))


# --------------------------------------------------------------------------- #
# pure parsing helpers
# --------------------------------------------------------------------------- #
def normalize_path(path: str) -> str:
    """Turn git's rename notation into the new path.

    ``src/{old => new}/a.py`` -> ``src/new/a.py``
    ``old.py => new.py``      -> ``new.py``
    """
    path = path.strip()
    if _BRACE_RENAME.search(path):
        path = _BRACE_RENAME.sub(lambda m: m.group(2), path)
        path = re.sub(r"/{2,}", "/", path).strip("/")
    elif " => " in path:
        path = path.split(" => ", 1)[1]
    return path


def parse_numstat_line(line: str) -> FileChange | None:
    parts = line.split("\t", 2)
    if len(parts) != 3:
        return None
    added, deleted, path = parts
    if added == "-" and deleted == "-":
        return FileChange(normalize_path(path), 0, 0, is_binary=True)
    try:
        return FileChange(normalize_path(path), int(added), int(deleted))
    except ValueError:
        return None


def parse_log(raw: str) -> list[Commit]:
    commits: list[Commit] = []
    for chunk in raw.split(RECORD_SEP):
        if not chunk.strip():
            continue
        lines = chunk.split("\n")
        fields = lines[0].split(FIELD_SEP)
        if len(fields) < 6:
            continue  # malformed header, skip rather than crash
        sha, name, email, date_str, parents, subject = fields[:6]
        try:
            authored_at = datetime.fromisoformat(date_str.strip())
        except ValueError:
            continue
        commit = Commit(
            sha=sha.strip(),
            author_name=name.strip() or "(unknown)",
            author_email=email.strip().lower() or "(no email)",
            authored_at=authored_at,
            parents=parents.split(),
            message=subject.strip(),
        )
        for line in lines[1:]:
            if line.strip():
                change = parse_numstat_line(line)
                if change:
                    commit.files.append(change)
        commits.append(commit)
    return commits
