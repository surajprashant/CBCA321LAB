import os
import re

import pytest

from app.importer import Importer, ImportError_, is_url, name_from_url
from app.git_parser import read_commits


@pytest.fixture
def importer(store, tmp_path):
    return Importer(store, str(tmp_path / "clones"))


# ---------------- Store ---------------- #
def test_save_commits_creates_contributors_and_merges_email_case(store, sample_repo):
    repo_id = store.create_repository("sample", "src", str(sample_repo), None)
    inserted = store.save_commits(repo_id, read_commits(str(sample_repo)))
    assert inserted == 6
    people = store.query("SELECT name, email FROM contributors ORDER BY email")
    assert [p["email"] for p in people] == ["alice@example.com", "bob@example.com",
                                            "carol@example.com"]
    # the most recent name wins: "Alice" -> "Alice Smith"
    assert people[0]["name"] == "Alice Smith"


def test_save_commits_is_idempotent(store, sample_repo):
    repo_id = store.create_repository("sample", "src", str(sample_repo), None)
    commits = read_commits(str(sample_repo))
    store.save_commits(repo_id, commits)
    assert store.save_commits(repo_id, commits) == 0
    assert store.get_repository(repo_id)["commit_count"] == 6


def test_file_changes_are_stored(store, sample_repo):
    repo_id = store.create_repository("sample", "src", str(sample_repo), None)
    store.save_commits(repo_id, read_commits(str(sample_repo)))
    paths = {r["path"] for r in store.query("SELECT path FROM file_changes")}
    assert paths == {"src/app.py", "docs/readme.md", "src/util.py",
                     "tests/test_app.py", "src/config.py"}


def test_delete_repository_cascades(store, sample_repo):
    repo_id = store.create_repository("sample", "src", str(sample_repo), None)
    store.save_commits(repo_id, read_commits(str(sample_repo)))
    store.delete_repository(repo_id)
    assert store.list_repositories() == []
    assert store.query("SELECT COUNT(*) AS n FROM commits")[0]["n"] == 0
    assert store.query("SELECT COUNT(*) AS n FROM file_changes")[0]["n"] == 0


# ---------------- Importer helpers ---------------- #
@pytest.mark.parametrize("source,expected", [
    ("https://github.com/pallets/flask.git", True),
    ("git@github.com:pallets/flask.git", True),
    ("ssh://git@host/repo", True),
    ("/home/me/project", False),
    ("C:\\code\\project", False),
])
def test_is_url(source, expected):
    assert is_url(source) is expected


def test_name_from_url():
    assert name_from_url("https://github.com/pallets/flask.git") == "flask"
    assert name_from_url("git@github.com:me/my-app") == "my-app"


# ---------------- Importer ---------------- #
def test_import_local_repository(importer, sample_repo):
    result = importer.import_source(str(sample_repo))
    assert result["created"] is True
    assert result["new_commits"] == 6
    repo = result["repository"]
    assert repo["name"] == "sample"
    assert repo["commit_count"] == 6 and repo["contributor_count"] == 3


def test_import_from_subfolder_uses_repo_root(importer, sample_repo):
    result = importer.import_source(str(sample_repo / "src"))
    assert result["repository"]["path"] == str(sample_repo)


def test_import_same_source_twice_refreshes_instead_of_duplicating(importer, sample_repo):
    importer.import_source(str(sample_repo))
    again = importer.import_source(str(sample_repo))
    assert again["created"] is False and again["new_commits"] == 0
    assert len(importer.store.list_repositories()) == 1


def test_refresh_imports_only_new_commits(importer, repo_builder):
    repo_builder.commit("A", "a@x", "2026-01-01T10:00:00+00:00", {"a.txt": "1\n"})
    repo_id = importer.import_source(str(repo_builder.path))["repository"]["id"]
    repo_builder.commit("B", "b@x", "2026-01-02T10:00:00+00:00", {"b.txt": "2\n"})
    repo_builder.commit("B", "b@x", "2026-01-03T10:00:00+00:00", {"b.txt": "2\n3\n"})
    result = importer.refresh(repo_id)
    assert result["new_commits"] == 2
    assert result["repository"]["commit_count"] == 3


def test_refresh_after_history_rewrite_rebuilds(importer, repo_builder):
    repo_builder.commit("A", "a@x", "2026-01-01T10:00:00+00:00", {"a.txt": "1\n"})
    repo_builder.commit("A", "a@x", "2026-01-02T10:00:00+00:00", {"a.txt": "1\n2\n"})
    repo_id = importer.import_source(str(repo_builder.path))["repository"]["id"]
    repo_builder._git("reset", "-q", "--hard", "HEAD~1")
    repo_builder.commit("C", "c@x", "2026-01-05T10:00:00+00:00", {"c.txt": "x\n"})
    result = importer.refresh(repo_id)
    assert result["repository"]["commit_count"] == 2
    assert {p["name"] for p in importer.store.query("SELECT name FROM contributors")} == {"A", "C"}


def test_import_empty_repository(importer, repo_builder):
    result = importer.import_source(str(repo_builder.path))
    assert result["repository"]["commit_count"] == 0
    repo_builder.commit("A", "a@x", "2026-01-01T10:00:00+00:00", {"a.txt": "1\n"})
    assert importer.refresh(result["repository"]["id"])["new_commits"] == 1


@pytest.mark.parametrize("bad", ["", "   ", "--upload-pack=evil", "/definitely/not/here"])
def test_import_rejects_bad_sources(importer, bad):
    with pytest.raises(ImportError_):
        importer.import_source(bad)


def test_import_rejects_plain_folder(importer, tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    with pytest.raises(ImportError_, match="Not a Git repository"):
        importer.import_source(str(folder))


@pytest.fixture
def allow_file_urls(monkeypatch):
    """Treat file:// as a URL so clone tests run offline against a local repo."""
    from app import importer as importer_module
    monkeypatch.setattr(importer_module, "URL_PATTERN", re.compile(r"^file://"))


def test_url_import_stores_no_source_code(importer, sample_repo, allow_file_urls):
    """Deliverable-1 security rule: only metadata is kept, the temporary clone is deleted."""
    result = importer.import_source(sample_repo.as_uri())
    assert result["repository"]["commit_count"] == 6
    assert result["repository"]["path"] == sample_repo.as_uri()
    assert os.listdir(importer.clone_dir) == []  # nothing left behind
    importer.refresh(result["repository"]["id"])
    assert os.listdir(importer.clone_dir) == []
    assert importer.delete(result["repository"]["id"])


def test_refresh_reads_new_commits_from_url(importer, repo_builder, allow_file_urls):
    repo_builder.commit("A", "a@x", "2026-01-01T10:00:00+00:00", {"a.txt": "1\n"})
    repo_id = importer.import_source(repo_builder.path.as_uri())["repository"]["id"]
    repo_builder.commit("B", "b@x", "2026-01-02T10:00:00+00:00", {"b.txt": "2\n"})
    assert importer.refresh(repo_id)["new_commits"] == 1


def test_bad_url_gives_friendly_error(importer, tmp_path, allow_file_urls):
    with pytest.raises(ImportError_, match="Could not clone"):
        importer.import_source((tmp_path / "nope").as_uri())
    assert os.listdir(importer.clone_dir) == []  # failed clone cleaned up too


def test_delete_never_touches_local_folder(importer, sample_repo):
    repo_id = importer.import_source(str(sample_repo))["repository"]["id"]
    assert importer.delete(repo_id)
    assert (sample_repo / "src" / "app.py").exists()
    assert not importer.delete(repo_id)


def test_contributor_ids_are_compact(store, sample_repo):
    """One contributor row per person, without burning ids on every commit."""
    repo_id = store.create_repository("sample", "src", str(sample_repo), None)
    store.save_commits(repo_id, read_commits(str(sample_repo)))
    ids = sorted(r["id"] for r in store.query("SELECT id FROM contributors"))
    assert ids == [1, 2, 3]
    assert store.contributor_in_repo(repo_id, 1) and not store.contributor_in_repo(repo_id, 99)
