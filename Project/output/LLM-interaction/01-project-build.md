# LLM Interaction 01 — Building the project end to end

- **Date:** 2026-11-24
- **Tool:** Claude (Anthropic)
- **Purpose:** Turn the Assessment-2 and Assessment-3 guidelines into a working project.

## Prompt

> (Attached: Project Assessment-2 Guideline, Project Assessment-3 Guideline)
>
> My project title: developer contribution visualizer
>
> Now GO. Make everything end to end.

## What the LLM produced

1. `output/Assessment-2.md`: title, components, layered architecture (Mermaid
   diagram), MVP features, users, component interfaces, DB schema, tech stack.
   Committed **before** any implementation, as the guideline requires.
2. Implementation, committed step by step:
   git log parser → SQLite store → importer (clone + incremental refresh) →
   analytics → REST API → dashboard UI (Chart.js) → demo data generator.
3. 94 pytest tests (parser, store/importer, analytics, API).
4. `README.md` with setup, API, architecture and learnings; `output/Assessment-3.md`
   with features, testing and a demo script.

## Problems found during the session and how they were fixed

| Problem | Fix |
|---|---|
| `ORDER BY additions` was ambiguous after a join (test failed) | Order by `SUM(f.additions + f.deletions)` |
| Contributor ids jumped (1, 2, 3, 10, 17…) because SQLite upsert used up an AUTOINCREMENT id per commit | Look the row up first, then insert or update |
| Heatmap card overflowed the page (seen in a screenshot) | `min-width: 0` on grid children, `minmax(0, 1fr)` columns |
| Unknown contributor page showed an empty dashboard | Server returns a proper 404 page |

## My review

<!-- Write a few lines in your own words: what you checked, what you changed,
     what you understood or would do differently. -->
