"""Shared fixtures: throwaway Git repositories with known history."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.store import Store  # noqa: E402


class RepoBuilder:
    """Creates commits with chosen author, date and file contents."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "commit.gpgsign", "false")

    def _git(self, *args: str, env: dict | None = None) -> str:
        full_env = {**os.environ, **(env or {})}
        return subprocess.run(
            ["git", *args], cwd=self.path, env=full_env,
            capture_output=True, text=True, check=True,
        ).stdout

    def commit(self, author: str, email: str, date: str, files: dict[str, str],
               message: str = "change", delete: tuple[str, ...] = ()) -> str:
        for name, content in files.items():
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            self._git("add", name)
        for name in delete:
            self._git("rm", "-q", name)
        env = {
            "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": date,
        }
        self._git("commit", "-q", "-m", message, env=env)
        return self._git("rev-parse", "HEAD").strip()

    def mv(self, old: str, new: str, author: str, email: str, date: str) -> str:
        (self.path / new).parent.mkdir(parents=True, exist_ok=True)
        self._git("mv", old, new)
        env = {"GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
               "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": email,
               "GIT_COMMITTER_DATE": date}
        self._git("commit", "-q", "-m", f"move {old}", env=env)
        return self._git("rev-parse", "HEAD").strip()


def lines(n: int, tag: str = "x") -> str:
    return "".join(f"{tag} line {i}\n" for i in range(n))


@pytest.fixture
def repo_builder(tmp_path):
    return RepoBuilder(tmp_path / "sample")


@pytest.fixture
def sample_repo(repo_builder):
    """3 authors, 6 commits, known numbers used across tests.

    alice: 3 commits (+10, +5, +3/-2)   bob: 2 commits (+4, +6)   carol: 1 commit (+2)
    """
    b = repo_builder
    b.commit("Alice", "alice@example.com", "2026-01-05T09:15:00+05:30",
             {"src/app.py": lines(10)}, "initial app")
    b.commit("Bob", "bob@example.com", "2026-01-05T22:40:00+05:30",
             {"docs/readme.md": lines(4, "d")}, "add docs")
    b.commit("Alice", "Alice@Example.com", "2026-01-12T10:00:00+05:30",
             {"src/util.py": lines(5, "u")}, "add util")
    b.commit("Bob", "bob@example.com", "2026-01-13T14:30:00+05:30",
             {"tests/test_app.py": lines(6, "t")}, "add tests")
    b.commit("Alice Smith", "alice@example.com", "2026-01-20T09:45:00+05:30",
             {"src/app.py": lines(8) + lines(3, "new")}, "extend app")
    b.commit("Carol", "carol@example.com", "2026-02-02T16:05:00+05:30",
             {"src/config.py": lines(2, "c")}, "config")
    return b.path


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "app.db"),
        "CLONE_DIR": str(tmp_path / "clones"),
    })
    return app


@pytest.fixture
def client(app):
    return app.test_client()
