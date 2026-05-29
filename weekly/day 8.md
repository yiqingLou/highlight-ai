# Day 8 · 2026-05-27 Wednesday

## Done
- extract_video_metadata() in services/video_processor.py — ffprobe wrapper for video metadata
- extract_frames() in services/video_processor.py — ffmpeg wrapper to extract JPG frames
- POST /api/tasks/{id}/extract-frames endpoint
- Verified end-to-end with test_video.mp4 (10s 720p): returns frame_count=10, files written to backend/frames/4/

## Key learnings
- subprocess.run() with capture_output for clean external tool wrapping
- Three-tier architecture solidified: routes → services → models
- Frame storage strategy: backend/frames/{task_id}/ (per-task isolation)

## Commits
- 52b4f89  add VideoProcessor service (ffprobe wrapper)
- c4069d9  POST /api/tasks auto-extracts video metadata
- 2892342  add frame extraction service + extract-frames API