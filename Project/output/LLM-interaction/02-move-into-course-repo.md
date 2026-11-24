# LLM Interaction 02 — Moving the project into the course repository

- **Date:** 2026-11-24
- **Tool:** Claude (Anthropic)

## Prompt

> i have a folder created named cbca321lab and in it contains another folder project.
> My email is surajprashant18@gmail.com
>
> Now do everything

## What the LLM did

1. Set the commit author e-mail to my GitHub e-mail on every commit.
2. Found that `CBCA321LAB` is already my lab Git repository (labs 1–5 + `Project/`), so it
   rewrote the project history so every file sits under `Project/`. The original commit
   order is kept, including Assessment-2 being committed before any code.
3. Read my Deliverable 1 (`1. Problem understanding.pdf`) and found a conflict: it says
   the system must **never clone or store source code locally**, but URL imports kept a
   full clone. Fixed: URLs are now read from a temporary *bare* clone that is deleted right
   after import; a new test checks nothing is left on disk.
4. Added `scripts/benchmark.py` for the Deliverable 1 performance requirement
   (10,000 commits in under 5 s): measured 2.91 s, pass.
5. Added section 9 to Assessment-2 listing every change from Deliverable 1 and why
   (git CLI instead of per-commit API calls, SQLite instead of PostgreSQL, Flask instead
   of FastAPI, OAuth deferred), and aligned the users with my Deliverable 1 stakeholders.
6. Committed only the `Project/` folder; my uncommitted changes in the lab folders were
   left alone.

## My review

<!-- Write a few lines in your own words. -->
