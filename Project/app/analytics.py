"""Analytics service: turns stored commits into the numbers the dashboard shows.

Conventions
-----------
* Merge commits are excluded from every count except ``summary()["merges"]``;
  they carry no line changes and would otherwise inflate maintainers.
* ``since`` / ``until`` are inclusive ``YYYY-MM-DD`` dates in the author's timezone.
* ``color_index`` is a contributor's all-time rank in the repository. The UI maps it
  to a fixed palette slot, so a person keeps the same colour when filters change.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from .store import Store

SORT_COLUMNS = {
    "commits": "commits DESC",
    "additions": "additions DESC",
    "deletions": "deletions DESC",
    "active_days": "active_days DESC",
    "last_day": "last_day DESC",
    "name": "name COLLATE NOCASE ASC",
}
GRANULARITIES = ("auto", "day", "week", "month")


def parse_day(value: str | None, field: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"'{field}' must be a date in YYYY-MM-DD format") from None


def bus_factor(commit_counts: list[int]) -> int:
    """Smallest number of people who together made at least half of the commits."""
    total = sum(commit_counts)
    if total == 0:
        return 0
    running = 0
    for people, count in enumerate(sorted(commit_counts, reverse=True), start=1):
        running += count
        if running * 2 >= total:
            return people
    return len(commit_counts)


def bucket_key(day: str, granularity: str) -> str:
    d = date.fromisoformat(day)
    if granularity == "week":
        return (d - timedelta(days=d.weekday())).isoformat()  # Monday of that week
    if granularity == "month":
        return d.strftime("%Y-%m")
    return d.isoformat()


def bucket_labels(first: str, last: str, granularity: str) -> list[str]:
    """Every bucket between two days, so gaps show up as zero instead of vanishing."""
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    labels: list[str] = []
    if granularity == "month":
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            labels.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return labels
    step = 7 if granularity == "week" else 1
    current = date.fromisoformat(bucket_key(first, granularity))
    while current <= end:
        labels.append(current.isoformat())
        current += timedelta(days=step)
    return labels


def choose_granularity(first: str, last: str) -> str:
    span = (date.fromisoformat(last) - date.fromisoformat(first)).days
    if span > 730:
        return "month"
    if span > 90:
        return "week"
    return "day"


def _csv_safe(value):
    """Stop names like '=HYPERLINK(...)' being run as formulas when opened in Excel."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


class Analytics:
    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _where(repo_id: int, since=None, until=None, contributor_id=None,
               merges: bool = False, alias: str = "c") -> tuple[str, list]:
        since, until = parse_day(since, "since"), parse_day(until, "until")
        if since and until and since > until:
            raise ValueError("'since' must be on or before 'until'")
        clauses, params = [f"{alias}.repo_id = ?"], [repo_id]
        if not merges:
            clauses.append(f"{alias}.is_merge = 0")
        if since:
            clauses.append(f"{alias}.day >= ?")
            params.append(since)
        if until:
            clauses.append(f"{alias}.day <= ?")
            params.append(until)
        if contributor_id is not None:
            clauses.append(f"{alias}.contributor_id = ?")
            params.append(contributor_id)
        return " AND ".join(clauses), params

    def color_map(self, repo_id: int) -> dict[int, int]:
        rows = self.store.query(
            """SELECT p.id, COUNT(c.id) AS n FROM contributors p
               LEFT JOIN commits c ON c.contributor_id = p.id AND c.is_merge = 0
               WHERE p.repo_id = ? GROUP BY p.id ORDER BY n DESC, p.id ASC""",
            (repo_id,),
        )
        return {row["id"]: index for index, row in enumerate(rows)}

    # ------------------------------------------------------------------ #
    # summary
    # ------------------------------------------------------------------ #
    def summary(self, repo_id: int, since=None, until=None) -> dict:
        where, params = self._where(repo_id, since, until)
        totals = self.store.query(
            f"""SELECT COUNT(*) AS commits, COUNT(DISTINCT contributor_id) AS contributors,
                       COALESCE(SUM(additions), 0) AS additions,
                       COALESCE(SUM(deletions), 0) AS deletions,
                       COUNT(DISTINCT day) AS active_days,
                       MIN(day) AS first_day, MAX(day) AS last_day
                FROM commits c WHERE {where}""",
            params,
        )[0]
        files = self.store.query(
            f"""SELECT COUNT(DISTINCT f.path) AS n FROM file_changes f
                JOIN commits c ON c.id = f.commit_id WHERE {where}""",
            params,
        )[0]["n"]
        m_where, m_params = self._where(repo_id, since, until, merges=True)
        merges = self.store.query(
            f"SELECT COUNT(*) AS n FROM commits c WHERE {m_where} AND c.is_merge = 1", m_params
        )[0]["n"]
        board = self.leaderboard(repo_id, since, until)
        top = board[0] if board else None
        return {
            **totals,
            "net_lines": totals["additions"] - totals["deletions"],
            "files_touched": files,
            "merges": merges,
            "bus_factor": bus_factor([row["commits"] for row in board]),
            "top_contributor": (
                {"id": top["contributor_id"], "name": top["name"], "share": top["share"]}
                if top else None
            ),
        }

    # ------------------------------------------------------------------ #
    # leaderboard
    # ------------------------------------------------------------------ #
    def leaderboard(self, repo_id: int, since=None, until=None, sort: str = "commits") -> list[dict]:
        if sort not in SORT_COLUMNS:
            raise ValueError(f"'sort' must be one of: {', '.join(SORT_COLUMNS)}")
        where, params = self._where(repo_id, since, until)
        rows = self.store.query(
            f"""SELECT p.id AS contributor_id, p.name, p.email,
                       COUNT(c.id) AS commits,
                       SUM(c.additions) AS additions, SUM(c.deletions) AS deletions,
                       COUNT(DISTINCT c.day) AS active_days,
                       MIN(c.day) AS first_day, MAX(c.day) AS last_day
                FROM commits c JOIN contributors p ON p.id = c.contributor_id
                WHERE {where}
                GROUP BY p.id
                ORDER BY {SORT_COLUMNS[sort]}, commits DESC, p.id ASC""",
            params,
        )
        total = sum(row["commits"] for row in rows)
        colors = self.color_map(repo_id)
        for row in rows:
            row["net_lines"] = row["additions"] - row["deletions"]
            row["share"] = round(100 * row["commits"] / total, 1) if total else 0.0
            row["color_index"] = colors.get(row["contributor_id"], 0)
        return rows

    # ------------------------------------------------------------------ #
    # timeline
    # ------------------------------------------------------------------ #
    def timeline(self, repo_id: int, since=None, until=None, granularity: str = "auto",
                 top: int = 5, contributor_id=None) -> dict:
        if granularity not in GRANULARITIES:
            raise ValueError(f"'granularity' must be one of: {', '.join(GRANULARITIES)}")
        top = max(1, min(int(top), 8))  # the palette has 8 slots; the rest fold into Others
        where, params = self._where(repo_id, since, until, contributor_id)
        rows = self.store.query(
            f"""SELECT c.day, c.contributor_id, COUNT(*) AS n FROM commits c
                WHERE {where} GROUP BY c.day, c.contributor_id""",
            params,
        )
        if not rows:
            return {"granularity": "day" if granularity == "auto" else granularity,
                    "labels": [], "series": []}
        first = parse_day(since, "since") or min(r["day"] for r in rows)
        last = parse_day(until, "until") or max(r["day"] for r in rows)
        if granularity == "auto":
            granularity = choose_granularity(first, last)
        labels = bucket_labels(first, last, granularity)
        position = {label: i for i, label in enumerate(labels)}

        totals: dict[int, int] = defaultdict(int)
        for r in rows:
            totals[r["contributor_id"]] += r["n"]
        ranked = sorted(totals, key=lambda cid: (-totals[cid], cid))
        shown = ranked[:top]
        names = {r["id"]: r["name"] for r in self.store.query(
            "SELECT id, name FROM contributors WHERE repo_id = ?", (repo_id,))}
        colors = self.color_map(repo_id)

        data = {cid: [0] * len(labels) for cid in shown}
        others = [0] * len(labels)
        for r in rows:
            slot = position[bucket_key(r["day"], granularity)]
            (data[r["contributor_id"]] if r["contributor_id"] in data else others)[slot] += r["n"]

        series = [{"contributor_id": cid, "name": names.get(cid, "?"),
                   "color_index": colors.get(cid, 0), "total": totals[cid], "data": data[cid]}
                  for cid in shown]
        if any(others):
            series.append({"contributor_id": None,
                           "name": f"Others ({len(ranked) - len(shown)})",
                           "color_index": None, "total": sum(others), "data": others})
        return {"granularity": granularity, "labels": labels, "series": series}

    # ------------------------------------------------------------------ #
    # heatmap
    # ------------------------------------------------------------------ #
    def heatmap(self, repo_id: int, contributor_id=None, since=None, until=None) -> dict:
        where, params = self._where(repo_id, since, until, contributor_id)
        matrix = [[0] * 24 for _ in range(7)]
        for row in self.store.query(
            f"SELECT weekday, hour, COUNT(*) AS n FROM commits c WHERE {where} "
            f"GROUP BY weekday, hour",
            params,
        ):
            matrix[row["weekday"]][row["hour"]] = row["n"]
        peak_value = max(max(r) for r in matrix)
        peak = None
        if peak_value:
            wd, hr = next((d, h) for d in range(7) for h in range(24) if matrix[d][h] == peak_value)
            peak = {"weekday": wd, "hour": hr, "commits": peak_value}
        return {"matrix": matrix, "max": peak_value, "peak": peak}

    # ------------------------------------------------------------------ #
    # contributor drill-down
    # ------------------------------------------------------------------ #
    def contributor_detail(self, repo_id: int, contributor_id: int, since=None, until=None) -> dict | None:
        person = self.store.query(
            "SELECT id, name, email FROM contributors WHERE id = ? AND repo_id = ?",
            (contributor_id, repo_id),
        )
        if not person:
            return None
        person = person[0]
        board = self.leaderboard(repo_id, since, until)
        stats = next((row for row in board if row["contributor_id"] == contributor_id), None)
        rank = board.index(stats) + 1 if stats else None
        where, params = self._where(repo_id, since, until, contributor_id)
        repo_where, repo_params = self._where(repo_id, since, until)

        top_files = self.store.query(
            f"""SELECT f.path, COUNT(*) AS changes, SUM(f.additions) AS additions,
                       SUM(f.deletions) AS deletions
                FROM file_changes f JOIN commits c ON c.id = f.commit_id
                WHERE {where} GROUP BY f.path
                ORDER BY changes DESC, additions + deletions DESC, f.path LIMIT 10""",
            params,
        )
        if top_files:
            marks = ",".join("?" * len(top_files))
            team = {r["path"]: r["lines"] for r in self.store.query(
                f"""SELECT f.path, SUM(f.additions + f.deletions) AS lines
                    FROM file_changes f JOIN commits c ON c.id = f.commit_id
                    WHERE {repo_where} AND f.path IN ({marks}) GROUP BY f.path""",
                [*repo_params, *[f["path"] for f in top_files]],
            )}
            for f in top_files:
                mine = f["additions"] + f["deletions"]
                f["ownership"] = round(100 * mine / team[f["path"]], 1) if team.get(f["path"]) else 0.0

        folders: dict[str, int] = defaultdict(int)
        for row in self.store.query(
            f"""SELECT f.path, SUM(f.additions + f.deletions) AS lines
                FROM file_changes f JOIN commits c ON c.id = f.commit_id
                WHERE {where} GROUP BY f.path""",
            params,
        ):
            folder = row["path"].split("/", 1)[0] if "/" in row["path"] else "(root)"
            folders[folder] += row["lines"]
        total_lines = sum(folders.values())
        top_folders = [
            {"folder": name, "lines": n,
             "share": round(100 * n / total_lines, 1) if total_lines else 0.0}
            for name, n in sorted(folders.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ]

        recent = self.store.query(
            f"""SELECT sha, day, message, additions, deletions, files_changed
                FROM commits c WHERE {where} ORDER BY ts DESC LIMIT 20""",
            params,
        )
        return {
            "contributor": person,
            "color_index": self.color_map(repo_id).get(contributor_id, 0),
            "rank": rank,
            "of": len(board),
            "stats": stats,
            "timeline": self.timeline(repo_id, since, until, contributor_id=contributor_id),
            "heatmap": self.heatmap(repo_id, contributor_id, since, until),
            "top_files": top_files,
            "top_folders": top_folders,
            "recent_commits": recent,
        }

    # ------------------------------------------------------------------ #
    # export
    # ------------------------------------------------------------------ #
    def export_csv(self, repo_id: int, since=None, until=None) -> str:
        columns = ["name", "email", "commits", "additions", "deletions", "net_lines",
                   "active_days", "first_day", "last_day", "share"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in self.leaderboard(repo_id, since, until):
            writer.writerow({k: _csv_safe(v) for k, v in row.items()})
        return buffer.getvalue()
