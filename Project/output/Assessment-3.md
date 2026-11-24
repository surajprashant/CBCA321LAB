# Assessment 3 — Working Mini-Project

**Project:** Developer Contribution Visualizer

## 1. Crucial features chosen

| # | Feature | Why it is crucial |
|---|---|---|
| 1 | **Repository import + incremental refresh** | Without reliable data nothing else works. |
| 2 | **Repository dashboard** (summary, timeline, leaderboard, heatmap, date filter) | The core answer to “who contributed what, and when”. |
| 3 | **Contributor drill-down** | Answers “what did *this* person work on?”, including file ownership. |

Built on the same layers (Assessment 3, step 4): **CSV export**, **bus factor**,
**stable per-person colours**, **demo data generator**.

## 2. Implemented from UI to business logic

| Feature | UI | API | Logic | Data |
|---|---|---|---|---|
| Import | `index.html`, `home.js` (form, toasts, refresh/remove buttons) | `POST /api/repos`, `POST /refresh`, `DELETE` | `Importer.import_source / refresh / delete` → `git_parser.read_commits` | `Store.create_repository`, `save_commits` |
| Dashboard | `repo.html`, `repo.js`, `common.js` (filters, KPI tiles, Chart.js timeline, heatmap, sortable table) | `/summary`, `/timeline`, `/contributors`, `/heatmap`, `/export.csv` | `Analytics.summary / timeline / leaderboard / heatmap / export_csv` | SQL aggregates over `commits`, `file_changes` |
| Drill-down | `contributor.html`, `contributor.js` | `/contributors/<cid>` | `Analytics.contributor_detail` (rank, top files, ownership %, folders, recent commits) | same tables, filtered by contributor |

## 3. Testing

`python3 -m pytest -v` → **95 passed**.

- Every test builds a real throwaway Git repository with fixed authors, dates and
  line counts (see `tests/conftest.py`), so expected numbers are hand-calculated.
- Edge cases covered: renamed and binary files, e-mail case differences, name
  changes, empty repositories, force-pushed history, bad paths/URLs, argument
  injection (`--upload-pack=…`), invalid dates and sort keys, empty date ranges,
  CSV formula injection, unknown ids (404), and **no source code left on disk after
  a URL import** (Deliverable 1 security requirement).
- Manual check: imported the demo repo, this project's own repo and public GitHub
  repositories (`pallets/itsdangerous`, 677 commits / 44 contributors;
  `pallets/flask`, 5,566 commits / 873 contributors in 4.1 s including download).

### Non-functional requirements from Deliverable 1

| Requirement | Result |
|---|---|
| 10,000 commits fetched and rendered in under 5 s | `scripts/benchmark.py`: import 2.88 s + dashboard queries 0.04 s = **2.91 s, PASS** |
| Store metadata only, never source code | Temporary bare clone deleted after import, checked by `test_url_import_stores_no_source_code` |
| Errors handled without crashing the frontend | Every API error returns `{"error": …}` (400/404); the UI shows it as a message |

## 4. Demo script (October 7)

1. `python3 run.py` → open http://127.0.0.1:5000
2. `python3 scripts/make_demo_repo.py demo-repo` (or have it ready) → import the path.
3. Dashboard: point out the summary tiles and bus factor, change the timeline to
   Monthly / Top 3, then click **Last 30 days**. Colours stay with the same people.
4. Sort the leaderboard by **Added**, then click a developer → drill-down page:
   working hours, folders, file ownership, recent commits.
5. **Export CSV** → open in Excel.
6. Make a commit in the demo repo, click **↻ Refresh** → “1 new commit imported”.
7. Import this project's own folder → our own team history.
8. Run `python3 -m pytest -v` to show the tests passing, and
   `python3 scripts/benchmark.py` for the 10,000-commit performance check.

## 5. Screenshots

See `docs/screenshots/`.
