"""Analytics on the sample repository (numbers documented in conftest.sample_repo)."""
import pytest

from app.analytics import (
    Analytics, bucket_key, bucket_labels, bus_factor, choose_granularity, parse_day,
)
from app.importer import Importer


@pytest.fixture
def loaded(store, sample_repo, tmp_path):
    repo_id = Importer(store, str(tmp_path / "c")).import_source(str(sample_repo))["repository"]["id"]
    analytics = Analytics(store)
    ids = {r["email"].split("@")[0]: r["id"] for r in store.query("SELECT id, email FROM contributors")}
    return analytics, repo_id, ids


# ---------------- pure helpers ---------------- #
@pytest.mark.parametrize("counts,expected", [
    ([], 0), ([5], 1), ([3, 2, 1], 1), ([1, 1, 1, 1], 2), ([2, 2, 2], 2), ([10, 9, 1], 1), ([9, 9, 2], 2),
])
def test_bus_factor(counts, expected):
    assert bus_factor(counts) == expected


def test_bucket_key():
    assert bucket_key("2026-01-08", "day") == "2026-01-08"
    assert bucket_key("2026-01-08", "week") == "2026-01-05"  # Thursday -> Monday
    assert bucket_key("2026-01-08", "month") == "2026-01"


def test_bucket_labels_fill_gaps():
    assert bucket_labels("2026-01-30", "2026-02-02", "day") == \
        ["2026-01-30", "2026-01-31", "2026-02-01", "2026-02-02"]
    assert bucket_labels("2025-11-15", "2026-02-01", "month") == \
        ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert bucket_labels("2026-01-07", "2026-01-20", "week") == ["2026-01-05", "2026-01-12",
                                                                 "2026-01-19"]


def test_choose_granularity():
    assert choose_granularity("2026-01-01", "2026-02-01") == "day"
    assert choose_granularity("2026-01-01", "2026-09-01") == "week"
    assert choose_granularity("2020-01-01", "2026-01-01") == "month"


def test_parse_day_validation():
    assert parse_day(None, "since") is None
    assert parse_day("2026-01-05", "since") == "2026-01-05"
    with pytest.raises(ValueError, match="since"):
        parse_day("05/01/2026", "since")


# ---------------- summary ---------------- #
def test_summary_totals(loaded):
    analytics, repo_id, _ = loaded
    s = analytics.summary(repo_id)
    assert s["commits"] == 6
    assert s["contributors"] == 3
    assert (s["additions"], s["deletions"], s["net_lines"]) == (30, 2, 28)
    assert s["active_days"] == 5
    assert s["files_touched"] == 5
    assert (s["first_day"], s["last_day"]) == ("2026-01-05", "2026-02-02")
    assert s["bus_factor"] == 1
    assert s["top_contributor"]["name"] == "Alice Smith"
    assert s["top_contributor"]["share"] == 50.0


def test_summary_with_date_range(loaded):
    analytics, repo_id, _ = loaded
    s = analytics.summary(repo_id, since="2026-01-10", until="2026-01-31")
    assert s["commits"] == 3 and s["contributors"] == 2


def test_summary_empty_range(loaded):
    analytics, repo_id, _ = loaded
    s = analytics.summary(repo_id, since="2030-01-01")
    assert s["commits"] == 0 and s["bus_factor"] == 0 and s["top_contributor"] is None


def test_since_after_until_is_rejected(loaded):
    analytics, repo_id, _ = loaded
    with pytest.raises(ValueError):
        analytics.summary(repo_id, since="2026-02-01", until="2026-01-01")


# ---------------- leaderboard ---------------- #
def test_leaderboard_default_order_and_numbers(loaded):
    analytics, repo_id, _ = loaded
    board = analytics.leaderboard(repo_id)
    assert [r["name"] for r in board] == ["Alice Smith", "Bob", "Carol"]
    alice = board[0]
    assert (alice["commits"], alice["additions"], alice["deletions"]) == (3, 18, 2)
    assert alice["active_days"] == 3
    assert [r["share"] for r in board] == [50.0, 33.3, 16.7]
    assert [r["color_index"] for r in board] == [0, 1, 2]


def test_leaderboard_sort_by_name(loaded):
    analytics, repo_id, _ = loaded
    assert [r["name"] for r in analytics.leaderboard(repo_id, sort="name")] == \
        ["Alice Smith", "Bob", "Carol"]
    assert analytics.leaderboard(repo_id, sort="last_day")[0]["name"] == "Carol"


def test_leaderboard_rejects_unknown_sort(loaded):
    analytics, repo_id, _ = loaded
    with pytest.raises(ValueError):
        analytics.leaderboard(repo_id, sort="DROP TABLE")


def test_colors_are_stable_when_filtering(loaded):
    """Bob leads in the filtered range but keeps his all-time colour."""
    analytics, repo_id, ids = loaded
    board = analytics.leaderboard(repo_id, since="2026-01-13", until="2026-01-13")
    assert board[0]["contributor_id"] == ids["bob"] and board[0]["color_index"] == 1


# ---------------- timeline ---------------- #
def test_timeline_weekly(loaded):
    analytics, repo_id, _ = loaded
    t = analytics.timeline(repo_id, granularity="week")
    assert t["labels"] == ["2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26", "2026-02-02"]
    by_name = {s["name"]: s["data"] for s in t["series"]}
    assert by_name["Alice Smith"] == [1, 1, 1, 0, 0]
    assert by_name["Bob"] == [1, 1, 0, 0, 0]
    assert by_name["Carol"] == [0, 0, 0, 0, 1]


def test_timeline_folds_extra_people_into_others(loaded):
    analytics, repo_id, _ = loaded
    t = analytics.timeline(repo_id, granularity="month", top=2)
    assert t["labels"] == ["2026-01", "2026-02"]
    assert [s["name"] for s in t["series"]] == ["Alice Smith", "Bob", "Others (1)"]
    assert t["series"][-1]["data"] == [0, 1] and t["series"][-1]["color_index"] is None


def test_timeline_auto_picks_day_for_short_history(loaded):
    analytics, repo_id, _ = loaded
    t = analytics.timeline(repo_id)
    assert t["granularity"] == "day" and len(t["labels"]) == 29
    assert sum(sum(s["data"]) for s in t["series"]) == 6


def test_timeline_empty(loaded):
    analytics, repo_id, _ = loaded
    assert analytics.timeline(repo_id, since="2030-01-01")["series"] == []


def test_timeline_bad_granularity(loaded):
    analytics, repo_id, _ = loaded
    with pytest.raises(ValueError):
        analytics.timeline(repo_id, granularity="year")


# ---------------- heatmap ---------------- #
def test_heatmap_counts_by_weekday_and_hour(loaded):
    analytics, repo_id, ids = loaded
    h = analytics.heatmap(repo_id)
    m = h["matrix"]
    assert len(m) == 7 and all(len(row) == 24 for row in m)
    assert sum(map(sum, m)) == 6
    assert m[0][9] == 1 and m[0][22] == 1 and m[1][14] == 1  # Mon 09h, Mon 22h, Tue 14h
    assert h["peak"] == {"weekday": 0, "hour": 9, "commits": 1}
    bob = analytics.heatmap(repo_id, contributor_id=ids["bob"])["matrix"]
    assert sum(map(sum, bob)) == 2 and bob[0][22] == 1


# ---------------- contributor detail ---------------- #
def test_contributor_detail(loaded):
    analytics, repo_id, ids = loaded
    d = analytics.contributor_detail(repo_id, ids["alice"])
    assert d["contributor"]["name"] == "Alice Smith"
    assert (d["rank"], d["of"]) == (1, 3)
    assert d["stats"]["commits"] == 3
    top = d["top_files"][0]
    assert top["path"] == "src/app.py" and top["changes"] == 2 and top["ownership"] == 100.0
    assert d["top_folders"] == [{"folder": "src", "lines": 20, "share": 100.0}]
    assert [c["message"] for c in d["recent_commits"]] == ["extend app", "add util", "initial app"]
    assert sum(sum(s["data"]) for s in d["timeline"]["series"]) == 3


def test_contributor_detail_unknown(loaded):
    analytics, repo_id, _ = loaded
    assert analytics.contributor_detail(repo_id, 9999) is None


def test_contributor_with_no_commits_in_range(loaded):
    analytics, repo_id, ids = loaded
    d = analytics.contributor_detail(repo_id, ids["carol"], until="2026-01-31")
    assert d["stats"] is None and d["rank"] is None and d["top_files"] == []


# ---------------- export ---------------- #
def test_export_csv(loaded):
    analytics, repo_id, _ = loaded
    rows = analytics.export_csv(repo_id).strip().splitlines()
    assert rows[0].startswith("name,email,commits")
    assert rows[1].startswith("Alice Smith,alice@example.com,3,18,2,16")
    assert len(rows) == 4


def test_export_csv_neutralises_formulas(store, repo_builder, tmp_path):
    repo_builder.commit("=HYPERLINK(\"x\")", "evil@x", "2026-01-01T10:00:00+00:00", {"a": "1\n"})
    repo_id = Importer(store, str(tmp_path / "c")).import_source(str(repo_builder.path))["repository"]["id"]
    csv_text = Analytics(store).export_csv(repo_id)
    assert "'=HYPERLINK" in csv_text
