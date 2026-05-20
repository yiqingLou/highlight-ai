# Day 3 · 2026-05-20 Wednesday

## Done today
- Designed complete database schema: 6 tables (tasks / highlights / clips / bgm / subtitles / settings)
- Wrote design/schema.md with full SQL DDL + indexes + seed data
- Understood SQL syntax: CREATE TABLE, NOT NULL, PRIMARY KEY, FOREIGN KEY, INDEX, CASCADE
- Understood system architecture: how frontend (Next.js), backend (FastAPI), database (SQLite), and file system talk to each other
- Pushed schema to GitHub

## Key concept insights
- Schema is just "code for the database" — you write it, the database reads it
- FastAPI turns Python functions into URLs the frontend can call
- SQLite = single-file database, perfect for local-first apps
- Splitting AI scores into combined + 3 sub-scores enables debugging the ranker later

## Day 4 plan (2026-05-21)
- Install Python 3.11, Node.js 20, FFmpeg
- Verify each by running Hello World
- Create FastAPI + Next.js skeleton projects
- Add architecture.md / ER diagram / project-structure to repo (carried from Day 3)