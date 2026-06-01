# Day 11 · 2026-06-01 Monday — Week 3 starts

## Done
- Added `update_task_status()` helper in routes/tasks.py
  - centralized state writes: status / progress / error_message
  - one place to change if state schema evolves
- Wired status lifecycle into POST /api/tasks/{id}/extract-frames:
  - on entry → status=processing, progress=30
  - on success → status=done, progress=100
  - on FileNotFoundError → status=failed + error_message
  - on VideoProbeError → status=failed + error_message
  - on FileExistsError → status=failed + error_message
- Added `status` field to extract-frames response body
- Verified end-to-end:
  - task=4 (real video) → status pending → done after extract
  - task=2 (fake path) → status pending → failed, error_message recorded

## Key learnings
- **Helper function pattern (DRY)**: same write logic in 4 places, factored into one function — easier to evolve later
- **State + side effect**: API returning 400 is not enough — DB should reflect what actually happened. "Returning an error code" and "recording the failure in state" are different commitments.
- **Failure paths deserve testing too**: success path passing != correctness. Day 11 spent equal time on the failure branch.

## Commits
- eb1c1a9  Day 11: add task status lifecycle with update_task_status helper

## Pending (Week 3 wrap-up)
- Day 6 daily report (still owed since 2026-05-25)
- Day 10 daily report (still owed)
- Rename weekly/day NN.md → weekly/day-NN.md for naming consistency

## Reflections
- First day back after cold + full weekend off. State "still okay", finished main task in 50 min.
- Took the "rest before pushing" lesson seriously — pace today felt sustainable, not heroic.