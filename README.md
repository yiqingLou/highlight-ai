# Naraka Highlight AI

Automatically turn raw Naraka: Bladepoint gameplay recordings into fully edited
highlight reels — kill detection, speed-ramp slow motion, beat-synced BGM,
animated captions, transitions, and a TikTok-ready vertical cut. Packaged as a
double-click Windows desktop app: no Python, no ffmpeg, no setup.

> 12-week solo project (June–August 2026). MVP shipped ahead of schedule.

## Features

- **AI kill detection** — a fine-tuned YOLO11 model finds every kill in a
	20-minute 2K/60fps recording at ~1s granularity
- **Auto editing** — per-kill clips with speed-ramp slow motion into the hit
- **Montage assembly** — ViralScore ranking picks and orders top moments,
	stitched with crossfade / flash-white transitions, animated kill captions,
	intro/outro title cards, and onset-synced background music (librosa)
- **Vertical export** — one click re-frames the reel to 1080×1920 with a
	blurred backdrop for TikTok / Shorts
- **Web UI** — drag-and-drop upload or zero-copy local path, real staged
	progress, clip selection & montage rebuild, library with search and posters
- **Desktop packaging** — PyInstaller onedir build bundling the model,
	ffmpeg/ffprobe, and frontend; runs fully offline on localhost

## The ML story

Early models collapsed on every new match (recall dropped to ~25%): the
annotation boxes included the victim avatar — a per-match variable. The scheme
was redesigned around **match-invariant UI elements** (two narrow strips on the
kill icon's border/mask/scratch edges, avatar excluded). The very next model
generalized **zero-shot** to a match it had never seen, and recall rose from
**25% to 92%+** across held-out matches. Later rounds added hard-negative
mining across four different matches to drive production false positives to
zero.

## Quick start (packaged app)

1. Download and unzip the release folder
2. Double-click `highlight-ai.exe` (a console window stays open — that's the
	 local server)
3. Open `http://127.0.0.1:8000/` in your browser
4. Drop a recording (or paste its path), press **Start Processing**, download
	 your reel

## Quick start (from source)

```bash
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Tech stack

FastAPI · SQLAlchemy/SQLite · ffmpeg · Ultralytics YOLO11 · librosa ·
PyInstaller · vanilla HTML/CSS/JS frontend

## Roadmap

- Additional game support (the schema already carries `game_type`)
- Auto-open browser on launch; installer packaging
- Union sampling mode (1fps + 2fps) for edge-case recall
