# Day 13 · 2026-06-03 Wednesday — List filtering + pagination + true async test

## Done

### Morning (3 steps committed separately)
- **Step 1**: GET /api/tasks now supports `?status=` query filter
  - 4 test scenarios passed (no filter / done / failed / nonexistent)
  - Commit: 4403def
- **Step 2**: Added `?game_type=` filter; both filters combine via AND
  - 4 scenarios passed including combined `?status=done&game_type=naraka`
  - Commit: b813573
- **Step 3**: Pagination with `?skip=` and `?limit=` 
  - `limit` capped server-side at 100 to prevent DoS
  - Response now includes `total_count` (across all pages) + `total` (this page)
  - 5 scenarios passed including `?limit=999` → forced to 100
  - Commit: b547162

### Afternoon: Real async validation
- Generated 3 test videos via ffmpeg: 10s / 60s / 300s (1080p 30fps)
- Created task=5 (60s video) and task=6 (300s video) via POST /api/tasks
- Triggered POST /api/tasks/6/extract-frames on the 5-minute video:
  - API returned 202 in <1 second (truly non-blocking) ✅
  - Background worker processed for ~30-60s
  - Final result: 300 JPG files written to backend/frames/6/
  - Database task status transitioned: pending -> processing -> done
  - GET /api/tasks/6/progress polling worked: 0% (waiting) -> 100% (completed)
- This is the first time the project handled a realistic-duration recording end-to-end.

## Key learnings
- **Query parameter composition**: SQLAlchemy `.filter().filter()` chains naturally for AND conditions
- **`total_count` vs `total`**: clients need both to render "Page X of Y" UI
- **Server-side limit cap (`limit > 100 -> limit = 100`)**: defense against pagination DoS, not optional in production
- **300 frames from a 5-minute 1080p video** confirmed the async + storage pipeline scales beyond toy data

## Catch from start of day
- Day 12 part 2 (progress endpoint) was committed locally but never pushed yesterday — caught by `git status` first thing this morning and recovered (commit a15e8f1).
- Pattern noted: I tend to skip the final `git push` step. New rule starting today: paste the `main -> main` line to confirm.

## Commits
- a15e8f1  Day 12 part 2: GET /api/tasks/{id}/progress endpoint (backfilled)
- 4403def  Day 13 Step 1: ?status= filter
- b813573  Day 13 Step 2: ?game_type= filter + multi-criteria
- b547162  Day 13 Step 3: pagination + abuse protection

## Reflections
- 2.5 hours of focused work accomplished what could have been a full day. Pace felt sustainable, not heroic.
- Skipped lunch (had a heavy breakfast). Will eat properly tomorrow.
- The "double confirmation" rule (paste `main -> main` after every push) is starting to feel automatic.

## Pending (Week 3 wrap-up)
- Day 6, Day 10, Day 12 daily reports still owed
- File naming consistency in weekly/ (some files use spaces)