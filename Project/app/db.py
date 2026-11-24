"""SQLite schema and connection helper."""
from __future__ import annotations

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    source       TEXT NOT NULL UNIQUE,   -- what the user typed (path or URL)
    path         TEXT NOT NULL,          -- working copy on disk
    head_sha     TEXT,                   -- last imported commit
    imported_at  TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contributors (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id   INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    email     TEXT NOT NULL,
    name      TEXT NOT NULL,
    name_ts   INTEGER NOT NULL DEFAULT 0, -- timestamp of the commit the name came from
    UNIQUE (repo_id, email)
);

CREATE TABLE IF NOT EXISTS commits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id         INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    contributor_id  INTEGER NOT NULL REFERENCES contributors(id) ON DELETE CASCADE,
    sha             TEXT NOT NULL,
    ts              INTEGER NOT NULL,     -- unix seconds (UTC)
    day             TEXT NOT NULL,        -- YYYY-MM-DD in the author's timezone
    weekday         INTEGER NOT NULL,     -- 0 = Monday
    hour            INTEGER NOT NULL,     -- 0-23 in the author's timezone
    message         TEXT NOT NULL,
    is_merge        INTEGER NOT NULL DEFAULT 0,
    additions       INTEGER NOT NULL DEFAULT 0,
    deletions       INTEGER NOT NULL DEFAULT 0,
    files_changed   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (repo_id, sha)
);

CREATE TABLE IF NOT EXISTS file_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_id  INTEGER NOT NULL REFERENCES commits(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,
    additions  INTEGER NOT NULL DEFAULT 0,
    deletions  INTEGER NOT NULL DEFAULT 0,
    is_binary  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_commits_repo_day ON commits(repo_id, day);
CREATE INDEX IF NOT EXISTS idx_commits_contributor ON commits(contributor_id);
CREATE INDEX IF NOT EXISTS idx_file_changes_commit ON file_changes(commit_id);
"""


def connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
