"""Data-access layer: every SQL statement that writes data lives here."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Iterator

from .db import connect, init_db
from .git_parser import Commit


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path
        init_db(db_path)

    @contextmanager
    def connection(self) -> Iterator:
        conn = connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # generic read helper used by the analytics layer
    # ------------------------------------------------------------------ #
    def query(self, sql: str, params: Iterable = ()) -> list[dict]:
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params))]

    # ------------------------------------------------------------------ #
    # repositories
    # ------------------------------------------------------------------ #
    _REPO_SELECT = """
        SELECT r.*,
               (SELECT COUNT(*) FROM commits c WHERE c.repo_id = r.id) AS commit_count,
               (SELECT COUNT(*) FROM contributors p WHERE p.repo_id = r.id) AS contributor_count
        FROM repositories r
    """

    def create_repository(self, name: str, source: str, path: str, head_sha: str | None) -> int:
        now = _now()
        with self.connection() as conn:
            cur = conn.execute(
                "INSERT INTO repositories (name, source, path, head_sha, imported_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (name, source, path, head_sha, now, now),
            )
            return cur.lastrowid

    def get_repository(self, repo_id: int) -> dict | None:
        rows = self.query(self._REPO_SELECT + " WHERE r.id = ?", (repo_id,))
        return rows[0] if rows else None

    def find_repository_by_source(self, source: str) -> dict | None:
        rows = self.query(self._REPO_SELECT + " WHERE r.source = ?", (source,))
        return rows[0] if rows else None

    def list_repositories(self) -> list[dict]:
        return self.query(self._REPO_SELECT + " ORDER BY r.updated_at DESC, r.id DESC")

    def update_head(self, repo_id: int, head_sha: str | None) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE repositories SET head_sha = ?, updated_at = ? WHERE id = ?",
                (head_sha, _now(), repo_id),
            )

    def delete_repository(self, repo_id: int) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))

    def clear_commits(self, repo_id: int) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM commits WHERE repo_id = ?", (repo_id,))
            conn.execute("DELETE FROM contributors WHERE repo_id = ?", (repo_id,))

    # ------------------------------------------------------------------ #
    # commits
    # ------------------------------------------------------------------ #
    def save_commits(self, repo_id: int, commits: list[Commit]) -> int:
        """Insert commits (skipping ones already stored). Returns number inserted."""
        inserted = 0
        with self.connection() as conn:
            contributor_ids: dict[str, int] = {}
            for commit in commits:
                ts = int(commit.authored_at.timestamp())
                conn.execute(
                    """INSERT INTO contributors (repo_id, email, name, name_ts) VALUES (?, ?, ?, ?)
                       ON CONFLICT(repo_id, email) DO UPDATE
                       SET name = excluded.name, name_ts = excluded.name_ts
                       WHERE excluded.name_ts > contributors.name_ts""",
                    (repo_id, commit.author_email, commit.author_name, ts),
                )
                if commit.author_email not in contributor_ids:
                    contributor_ids[commit.author_email] = conn.execute(
                        "SELECT id FROM contributors WHERE repo_id = ? AND email = ?",
                        (repo_id, commit.author_email),
                    ).fetchone()["id"]

                local = commit.authored_at
                cur = conn.execute(
                    """INSERT OR IGNORE INTO commits
                       (repo_id, contributor_id, sha, ts, day, weekday, hour, message,
                        is_merge, additions, deletions, files_changed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        repo_id, contributor_ids[commit.author_email], commit.sha, ts,
                        local.strftime("%Y-%m-%d"), local.weekday(), local.hour,
                        commit.message, int(commit.is_merge), commit.additions,
                        commit.deletions, len(commit.files),
                    ),
                )
                if cur.rowcount == 0:
                    continue  # already imported
                inserted += 1
                conn.executemany(
                    "INSERT INTO file_changes (commit_id, path, additions, deletions, is_binary)"
                    " VALUES (?, ?, ?, ?, ?)",
                    [
                        (cur.lastrowid, f.path, f.additions, f.deletions, int(f.is_binary))
                        for f in commit.files
                    ],
                )
        return inserted
