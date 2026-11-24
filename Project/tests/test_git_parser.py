from app.git_parser import (
    FIELD_SEP, RECORD_SEP, GitError, head_sha, is_git_repo, normalize_path,
    parse_log, parse_numstat_line, read_commits, run_git,
)
import pytest


def header(sha, name, email, date, parents="", subject="msg"):
    return RECORD_SEP + FIELD_SEP.join([sha, name, email, date, parents, subject])


# ---------------- normalize_path ---------------- #
@pytest.mark.parametrize("raw,expected", [
    ("src/app.py", "src/app.py"),
    ("old.py => new.py", "new.py"),
    ("src/{old => new}/a.py", "src/new/a.py"),
    ("src/{ => sub}/a.py", "src/sub/a.py"),
    ("src/{sub => }/a.py", "src/a.py"),
    ("{lib => src}/x.js", "src/x.js"),
])
def test_normalize_path_handles_renames(raw, expected):
    assert normalize_path(raw) == expected


# ---------------- parse_numstat_line ---------------- #
def test_numstat_text_file():
    change = parse_numstat_line("12\t3\tsrc/app.py")
    assert (change.path, change.additions, change.deletions, change.is_binary) == \
        ("src/app.py", 12, 3, False)


def test_numstat_binary_file():
    change = parse_numstat_line("-\t-\tlogo.png")
    assert change.is_binary and change.additions == 0 and change.deletions == 0


def test_numstat_garbage_returns_none():
    assert parse_numstat_line("not a numstat line") is None
    assert parse_numstat_line("x\ty\tz") is None


# ---------------- parse_log ---------------- #
def test_parse_log_reads_fields_and_files():
    raw = (
        header("a1", "Alice", "ALICE@X.COM", "2026-03-01T10:20:00+05:30", "p0", "first")
        + "\n4\t1\tsrc/a.py\n-\t-\timg.png\n"
        + header("b2", "Bob", "bob@x.com", "2026-03-02T23:00:00+00:00", "p1 p2", "Merge x")
        + "\n"
    )
    commits = parse_log(raw)
    assert [c.sha for c in commits] == ["a1", "b2"]
    first = commits[0]
    assert first.author_email == "alice@x.com"  # normalised to lower case
    assert first.additions == 4 and first.deletions == 1
    assert len(first.files) == 2 and first.files[1].is_binary
    assert first.authored_at.hour == 10  # keeps author's own timezone
    assert commits[1].is_merge and not first.is_merge


def test_parse_log_skips_malformed_records():
    raw = RECORD_SEP + "only-one-field\n" + header("c3", "C", "c@x", "not-a-date") + \
        header("d4", "D", "d@x", "2026-01-01T00:00:00+00:00")
    commits = parse_log(raw)
    assert [c.sha for c in commits] == ["d4"]


def test_parse_log_empty_input():
    assert parse_log("") == []


def test_missing_name_and_email_get_placeholders():
    commits = parse_log(header("e5", "", "", "2026-01-01T00:00:00+00:00"))
    assert commits[0].author_name == "(unknown)"
    assert commits[0].author_email == "(no email)"


# ---------------- real git repositories ---------------- #
def test_read_commits_from_real_repo(sample_repo):
    commits = read_commits(str(sample_repo))
    assert len(commits) == 6
    newest = commits[0]  # git log is newest first
    assert newest.author_name == "Carol"
    extend = next(c for c in commits if c.message == "extend app")
    assert (extend.additions, extend.deletions) == (3, 2)


def test_read_commits_since_sha_returns_only_new(repo_builder):
    first = repo_builder.commit("A", "a@x", "2026-01-01T10:00:00+00:00", {"a.txt": "1\n"})
    repo_builder.commit("B", "b@x", "2026-01-02T10:00:00+00:00", {"b.txt": "2\n"})
    new = read_commits(str(repo_builder.path), since_sha=first)
    assert [c.author_name for c in new] == ["B"]


def test_renamed_file_is_reported_under_new_path(repo_builder):
    repo_builder.commit("A", "a@x", "2026-01-01T10:00:00+00:00", {"lib/x.py": "1\n2\n"})
    repo_builder.mv("lib/x.py", "src/x.py", "A", "a@x", "2026-01-02T10:00:00+00:00")
    moved = read_commits(str(repo_builder.path))[0]
    assert moved.files[0].path == "src/x.py"
    assert moved.additions == 0  # a pure rename is not counted as new lines


def test_empty_repo_has_no_commits(repo_builder):
    assert head_sha(str(repo_builder.path)) is None
    assert read_commits(str(repo_builder.path)) == []


def test_is_git_repo(tmp_path, sample_repo):
    assert is_git_repo(str(sample_repo))
    assert not is_git_repo(str(tmp_path / "missing"))
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not is_git_repo(str(plain))


def test_run_git_raises_on_failure(tmp_path):
    with pytest.raises(GitError):
        run_git(["log"], cwd=str(tmp_path))
