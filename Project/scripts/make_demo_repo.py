"""Create a realistic demo repository with several developers and ~8 months of history.

    python scripts/make_demo_repo.py            # creates ./demo-repo
    python scripts/make_demo_repo.py /tmp/demo  # or any empty folder

The history is random but reproducible (fixed seed), so every demo looks the same.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

# name, email, share of commits, typical working hours, favourite folders
DEVELOPERS = [
    ("Aarav Mehta", "aarav@demo.dev", 0.30, range(10, 19), ["backend", "api"]),
    ("Priya Nair", "priya@demo.dev", 0.24, range(21, 24), ["frontend", "ui"]),
    ("Rohan Gupta", "rohan@demo.dev", 0.18, range(9, 13), ["backend", "db"]),
    ("Sneha Iyer", "sneha@demo.dev", 0.13, range(14, 20), ["tests", "backend"]),
    ("Kabir Singh", "kabir@demo.dev", 0.09, range(0, 3), ["docs", "frontend"]),
    ("Meera Joshi", "meera@demo.dev", 0.06, range(11, 17), ["ci", "docs"]),
]
FILES = {
    "backend": ["backend/app.py", "backend/models.py", "backend/services.py", "backend/auth.py"],
    "api": ["api/routes.py", "api/schemas.py"],
    "frontend": ["frontend/index.html", "frontend/app.js", "frontend/style.css"],
    "ui": ["frontend/components/chart.js", "frontend/components/table.js"],
    "db": ["db/schema.sql", "db/migrations/001_init.sql", "db/seed.sql"],
    "tests": ["tests/test_app.py", "tests/test_models.py", "tests/test_api.py"],
    "docs": ["README.md", "docs/setup.md", "docs/architecture.md"],
    "ci": [".github/workflows/ci.yml", "Makefile"],
}
VERBS = ["Add", "Fix", "Refactor", "Update", "Improve", "Clean up", "Implement", "Tweak"]
NOUNS = ["login flow", "chart colours", "API validation", "user model", "README", "CI pipeline",
         "error handling", "date filter", "leaderboard", "query performance", "unit tests", "layout"]


def git(repo: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env={**os.environ, **(env or {})})


def main(target: str = "demo-repo", commits: int = 320) -> None:
    repo = Path(target).resolve()
    if repo.exists() and any(repo.iterdir()):
        sys.exit(f"{repo} already exists and is not empty")
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")

    rng = random.Random(42)
    start = datetime(2026, 3, 2, tzinfo=IST)
    weights = [d[2] for d in DEVELOPERS]
    day_offsets = sorted(rng.randint(0, 240) for _ in range(commits))

    for i, offset in enumerate(day_offsets):
        name, email, _, hours, areas = rng.choices(DEVELOPERS, weights)[0]
        day = start + timedelta(days=offset)
        if day.weekday() >= 5 and rng.random() < 0.6:  # fewer weekend commits
            day += timedelta(days=7 - day.weekday())
        when = day.replace(hour=rng.choice(list(hours)), minute=rng.randint(0, 59))
        area = rng.choice(areas) if rng.random() < 0.85 else rng.choice(list(FILES))
        for path in rng.sample(FILES[area], k=min(len(FILES[area]), rng.randint(1, 2))):
            file = repo / path
            file.parent.mkdir(parents=True, exist_ok=True)
            existing = file.read_text().splitlines() if file.exists() else []
            remove = rng.randint(0, min(len(existing), 6))
            for _ in range(remove):
                existing.pop(rng.randrange(len(existing)))
            existing += [f"// {name.split()[0].lower()} change {i}.{n}" for n in range(rng.randint(2, 40))]
            file.write_text("\n".join(existing) + "\n")
            git(repo, "add", path)
        stamp = when.isoformat()
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": stamp,
               "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": stamp}
        git(repo, "commit", "-q", "-m", f"{rng.choice(VERBS)} {rng.choice(NOUNS)}", env=env)

    print(f"Demo repository with {commits} commits created at: {repo}")
    print("Import this path on the home page of the visualizer.")


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["demo-repo"]))
