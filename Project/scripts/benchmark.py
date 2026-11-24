"""Check the Deliverable-1 performance requirement:
"Fetching and rendering data for a repository with up to 10,000 commits must complete
in under 5 seconds."

    python scripts/benchmark.py          # 10,000 commits
    python scripts/benchmark.py 20000    # any size

Builds a synthetic repository with `git fast-import` (seconds, not minutes), then times
the import and every dashboard query against a throwaway database.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics import Analytics  # noqa: E402
from app.importer import Importer  # noqa: E402
from app.store import Store  # noqa: E402

AUTHORS = [("Aarav Mehta", "aarav@demo.dev"), ("Priya Nair", "priya@demo.dev"),
           ("Rohan Gupta", "rohan@demo.dev"), ("Sneha Iyer", "sneha@demo.dev"),
           ("Kabir Singh", "kabir@demo.dev"), ("Meera Joshi", "meera@demo.dev"),
           ("Dev Patel", "dev@demo.dev"), ("Isha Rao", "isha@demo.dev")]
FILES = [f"{folder}/file{n}.py" for folder in ("api", "core", "ui", "tests", "docs") for n in range(8)]


def build_repo(path: Path, commits: int) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    rng = random.Random(7)
    contents = {f: [] for f in FILES}
    start = 1_735_689_600  # 2025-01-01
    stream = []
    for i in range(commits):
        name, email = rng.choice(AUTHORS)
        ts = start + i * 3_000 + rng.randint(0, 2_000)
        changed = rng.sample(FILES, rng.randint(1, 3))
        msg = f"change {i}".encode()
        stream.append(f"commit refs/heads/main\nmark :{i + 1}\n"
                      f"author {name} <{email}> {ts} +0530\ncommitter {name} <{email}> {ts} +0530\n"
                      f"data {len(msg)}\n".encode() + msg + b"\n")
        if i:
            stream.append(f"from :{i}\n".encode())
        for f in changed:
            lines = contents[f]
            for _ in range(min(len(lines), rng.randint(0, 3))):
                lines.pop(rng.randrange(len(lines)))
            lines += [f"line {i}-{k}" for k in range(rng.randint(1, 12))]
            body = ("\n".join(lines) + "\n").encode()
            stream.append(f"M 100644 inline {f}\ndata {len(body)}\n".encode() + body + b"\n")
        stream.append(b"\n")
    subprocess.run(["git", "fast-import", "--quiet"], cwd=path, input=b"".join(stream), check=True)


def main(commits: int = 10_000) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "bench"
        t = time.perf_counter()
        build_repo(repo, commits)
        print(f"Built test repository with {commits:,} commits in {time.perf_counter() - t:.1f}s")

        store = Store(os.path.join(tmp, "bench.db"))
        importer, analytics = Importer(store, os.path.join(tmp, "tmp")), Analytics(store)

        t0 = time.perf_counter()
        repo_id = importer.import_source(str(repo))["repository"]["id"]
        t1 = time.perf_counter()
        analytics.summary(repo_id)
        analytics.leaderboard(repo_id)
        analytics.timeline(repo_id)
        analytics.heatmap(repo_id)
        t2 = time.perf_counter()

        total = t2 - t0
        print(f"Import (git log + parse + save): {t1 - t0:.2f}s")
        print(f"Dashboard queries (4 endpoints): {t2 - t1:.2f}s")
        print(f"Total: {total:.2f}s  ->  {'PASS' if total < 5 else 'FAIL'} (requirement: < 5s)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10_000)
