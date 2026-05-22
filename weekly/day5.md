# Day 5 · 2026-05-22 Friday — Week 1 Finale

## Done today

- **FFmpeg performance benchmark** on synthetic 30-min 1080p60 video:
  - CPU encode (libx264 medium): 4.49x speed, 6:41 elapsed, 73MB output
  - GPU encode (h264_nvenc p4 default): 8.02x speed, 3:44 elapsed, 264MB
  - GPU encode (h264_nvenc + bitrate cap): 7.95x, 3:46, 145MB
  - Frame extraction (1 fps): 55.2x speed, 32.6s for 30 min
- **Frontend-backend integration** — Connected Next.js to FastAPI via REST
  - Added CORS middleware to FastAPI
  - Built /api/highlights endpoint returning 5 fake highlight objects
  - Wrote React component with useEffect + fetch + useState
  - First true end-to-end working state
- (afternoon) Set up real SQLite database with SQLAlchemy ORM, replaced FAKE_HIGHLIGHTS with DB queries

## Reflections

- NVENC faster but lower-density — needs ~2x bitrate to match libx264 quality
- Frame extraction (not encoding) is the project bottleneck — and it's 55x speed
- "Fake data first, real implementation later" is going to be the pattern for Weeks 2-4

## Week 2 plan (5/25 Monday)

- Expand FastAPI structure (proper routes/services/models folders)
- Implement file upload endpoint
- Start video_processor service wrapping FFmpeg

## Mood

From "an idea on Monday" to "a full-stack app talking to a real database" in 5 days. Week 1 done.