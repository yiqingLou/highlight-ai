# Project Structure — highlight-ai

> Last updated: 2026-05-20 (Day 3)
> A guide to what lives where in this repo.

---

## Quick Reference

```
highlight-ai/
├── .gitignore              Git exclusion rules
├── README.md               Project homepage (GitHub front page)
├── PRD.md                  Product Requirements Document
├── competitors.md          Competitor research
├── INSTALL.md              Installation guide (Week 10)
├── LICENSE                 License file
│
├── design/                 All design artifacts
├── docs/                   Plans, retros, decisions
├── weekly/                 Daily logs
├── backend/                FastAPI server (Python)
├── frontend/               Next.js app (TypeScript)
├── desktop/                Tauri wrapper (Rust)
├── ml/                     ML models & experiments
├── data/                   Datasets (mostly gitignored)
├── scripts/                Setup & utility scripts
├── tests/                  End-to-end tests
└── .github/                GitHub config (CI, templates)
```

---

## Top-Level Files

| File | Purpose | When to update |
|---|---|---|
| `README.md` | The project homepage on GitHub. First thing people see. | Week 12 polish |
| `PRD.md` | Product Requirements Document. What we're building and why. | Whenever scope changes |
| `competitors.md` | Competitor analysis. CapCut, Outplayed, Medal, etc. | One-time, ~Day 1 |
| `INSTALL.md` | Step-by-step install guide for end users. | Week 10 |
| `LICENSE` | License terms. | Week 12 (or sooner) |
| `.gitignore` | Files Git should never track (secrets, videos, caches). | When you add new tools |

---

## `design/` — All Design Artifacts

Everything related to designing the product before writing code.

```
design/
├── wireframes/                  12 hand-drawn UI mockups
│   ├── 01-home.png
│   ├── 02-uploading.png
│   ├── 03-ai-processing.png
│   ├── 04-result-list.png
│   ├── 05-single-preview.png
│   ├── 06-timeline-edit.png
│   ├── 07-bgm-select.png
│   ├── 08-export.png
│   ├── 09-empty-state.png
│   ├── 10-error-state.png
│   ├── 11-task-list.png
│   └── 12-settings.png
│
├── schema.md                    Database schema (6 tables, SQL DDL)
├── architecture.md              System architecture overview
├── er-diagram.svg               ER diagram (vector, editable)
├── er-diagram.png               ER diagram (raster, for embedding)
└── user-flow.md                 User flow diagrams (optional)
```

**Use when**: any time you need to recall "what was the design intent" before implementing.

---

## `docs/` — Plans, Retros, Decisions

```
docs/
├── 12-week-plan.md              Full daily breakdown of 12 weeks
├── tech-decisions.md            Records of major tech choices (why FastAPI? why SQLite?)
├── monthly-1.md                 End-of-Week-4 retrospective
├── monthly-2.md                 End-of-Week-8 retrospective
└── final-retro.md               End-of-Week-12 retrospective
```

**Use when**: writing the blog posts at the end + interview prep.

---

## `weekly/` — Daily Work Logs

```
weekly/
├── day-01.md                    Mon  · Project kickoff + PRD
├── day-02.md                    Tue  · 12 wireframes + GitHub setup
├── day-03.md                    Wed  · Database schema + architecture
├── day-04.md                    Thu  · Environment setup
├── day-05.md                    Fri  · FFmpeg performance test
└── ...                          (60 total work days)
```

**Format**: short daily log, 5-10 min to write before clocking out.
**Use when**: reviewing what was done. Critical for resume + interview stories.

---

## `backend/` — FastAPI Server (Python)

The "brain" of the app. Handles AI, video processing, database operations.

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  FastAPI entry point — starts the server
│   ├── config.py                App-wide config (paths, GPU, model versions)
│   ├── database.py              SQLAlchemy DB connection + setup
│   │
│   ├── routes/                  REST API endpoints
│   │   ├── tasks.py             POST /api/tasks, GET /api/tasks/:id
│   │   ├── highlights.py        PATCH /api/highlights/:id
│   │   ├── clips.py             POST /api/clips (export)
│   │   ├── bgm.py               GET /api/bgm
│   │   └── settings.py          GET/PATCH /api/settings
│   │
│   ├── services/                Business logic (the "doers")
│   │   ├── video_processor.py   FFmpeg wrapper (cut, concat, encode)
│   │   ├── ocr_detector.py      Detect kill feed via PaddleOCR
│   │   ├── audio_detector.py    Find cheer / explosion peaks (librosa)
│   │   ├── visual_detector.py   Detect motion/brightness peaks (OpenCV)
│   │   ├── highlight_ranker.py  Combine OCR/audio/visual scores
│   │   ├── clip_assembler.py    Assemble final video (cuts + BGM + subs)
│   │   ├── subtitle_gen.py      Generate subtitles via Whisper
│   │   ├── tts_narrator.py      Generate commentary voice (Edge TTS)
│   │   └── viral_scorer.py      ViralScore prediction model
│   │
│   ├── models/                  SQLAlchemy ORM models (Python ↔ DB mapping)
│   │   ├── task.py              Task model (matches tasks table)
│   │   ├── highlight.py
│   │   ├── clip.py
│   │   ├── bgm.py
│   │   └── setting.py
│   │
│   ├── game_profiles/           Per-game detection configs (plugin pattern)
│   │   ├── base.py              GameProfile abstract base class
│   │   ├── naraka.py            Naraka Bladepoint config
│   │   ├── lol.py               League of Legends config
│   │   └── overwatch.py         Overwatch config
│   │
│   └── utils/                   Shared utilities
│       ├── logger.py            Logging setup
│       ├── exceptions.py        Custom exception classes
│       └── helpers.py           Misc helper functions
│
├── tests/                       Unit tests
│   ├── test_video_processor.py
│   ├── test_ocr.py
│   └── test_highlight_ranker.py
│
├── assets/                      Backend static assets
│   └── bgm/                     Pre-loaded BGM library (mp3 files)
│
├── requirements.txt             Python dependencies (pip install -r)
├── pyproject.toml               Python project config
├── .env.example                 Template for environment variables
└── README.md                    Backend-specific setup notes
```

**Run locally**: `cd backend && uvicorn app.main:app --reload --port 8000`

---

## `frontend/` — Next.js App (TypeScript)

The "face" of the app. Everything the user sees and clicks.

```
frontend/
├── app/                         Next.js App Router pages
│   ├── layout.tsx               Root layout (nav bar, theme)
│   ├── page.tsx                 Home screen (wireframe 1)
│   ├── tasks/
│   │   ├── page.tsx             Task list (wireframe 11)
│   │   └── [id]/
│   │       └── page.tsx         Task detail + highlights (wireframes 4-7)
│   └── settings/
│       └── page.tsx             Settings (wireframe 12)
│
├── components/                  Reusable UI components
│   ├── upload-zone.tsx          Drag & drop zone (used in wireframe 1, 9)
│   ├── progress-bar.tsx         Used in wireframes 2, 3
│   ├── highlight-list.tsx       Used in wireframe 4
│   ├── timeline-editor.tsx      Used in wireframe 6
│   ├── bgm-picker.tsx           Used in wireframe 7
│   ├── export-dialog.tsx        Used in wireframe 8
│   └── ui/                      shadcn/ui base components (auto-generated)
│
├── lib/                         Frontend utilities
│   ├── api.ts                   Backend API client (calls FastAPI)
│   ├── utils.ts                 Misc helpers
│   └── types.ts                 TypeScript types (Task, Highlight, etc.)
│
├── public/                      Static files served as-is
│   ├── logo.svg
│   └── icons/
│
├── package.json                 npm dependencies
├── tsconfig.json                TypeScript config
├── tailwind.config.js           Tailwind CSS config
├── next.config.js               Next.js config
└── README.md                    Frontend-specific setup notes
```

**Run locally**: `cd frontend && npm run dev` → http://localhost:3000

---

## `desktop/` — Tauri Desktop Wrapper (Rust)

Bundles frontend + backend into a single .exe / .app. Week 10 work.

```
desktop/
├── src-tauri/
│   ├── src/
│   │   └── main.rs              Rust entry — launches backend + opens window
│   ├── Cargo.toml               Rust dependencies
│   ├── tauri.conf.json          App config (name, icon, window size, perms)
│   └── icons/                   App icons (.ico for Windows, .icns for Mac)
└── README.md
```

**Build .exe**: `cd desktop && cargo tauri build` → creates installer in `target/`

---

## `ml/` — Machine Learning Models & Experiments

Training scripts, Jupyter notebooks, model configs.

```
ml/
├── yolo/                        YOLO kill-feed detection
│   ├── train.py                 Training script
│   ├── evaluate.py              Evaluation on test set
│   ├── export.py                Export to ONNX format
│   └── configs/
│       └── naraka.yaml          Per-game training config
│
├── ocr/                         OCR configuration
│   └── paddleocr_config.py
│
├── viral_score/                 ViralScore model
│   ├── features.py              Feature extraction
│   ├── train.py                 Train classifier
│   └── predict.py               Inference
│
└── notebooks/                   Jupyter experiments (read like a lab notebook)
    ├── 01-explore-ffmpeg.ipynb
    ├── 02-ocr-baseline.ipynb
    ├── 03-audio-analysis.ipynb
    └── 04-fusion-tuning.ipynb
```

**Use when**: tuning models, running experiments, writing blog posts about technical work.

---

## `data/` — Datasets

Most contents are gitignored (too large) — only metadata and small samples committed.

```
data/
├── samples/                     Small demo recordings (≤ 50MB, committed)
├── raw/                         Large training recordings (gitignored)
├── annotations/                 Labels for training
│   └── naraka_killfeed.json     Bounding boxes for YOLO training
└── README.md                    Where the data came from, how to download
```

---

## `scripts/` — Setup & Utility Scripts

```
scripts/
├── setup.bat                    Windows one-time install
├── setup.sh                     Mac/Linux one-time install
├── start.bat                    Windows launcher
├── start.sh                     Mac/Linux launcher
└── download_models.py           Download pre-trained model weights
```

---

## `tests/` — End-to-End Tests

```
tests/
├── e2e/                         End-to-end test cases
└── README.md
```

**Note**: Unit tests live next to the code in `backend/tests/`. This folder is for integration tests crossing frontend ↔ backend ↔ DB.

---

## `.github/` — GitHub Config

```
.github/
├── workflows/                   GitHub Actions (CI/CD)
│   └── test.yml                 Run tests on every push
└── ISSUE_TEMPLATE/              Bug report / feature request templates
```

---

## How Things Talk to Each Other

```
User
  ↓ clicks button
frontend/app/page.tsx
  ↓ uses
frontend/components/upload-zone.tsx
  ↓ calls
frontend/lib/api.ts (fetch http://localhost:8000/api/tasks)
  ↓ HTTP POST
backend/app/routes/tasks.py
  ↓ uses
backend/app/services/video_processor.py
  ↓ queries
backend/app/models/task.py (SQLAlchemy ORM)
  ↓ writes
SQLite database (~/AppData/HighlightAI/database.db)
```

**Frontend never touches the database directly.**  
**Backend never touches the DOM.**  
**Database knows nothing about HTTP.**

This separation is what makes the project maintainable.

---

## Week-by-Week Growth

This structure is the **finished state** by Week 12. Most folders start empty:

| Week | What gets filled in |
|---|---|
| 1 (current) | `design/`, `docs/`, `weekly/`, `.gitignore`, top-level docs |
| 2 | `backend/app/main.py`, `frontend/app/page.tsx` (skeletons) |
| 3 | `backend/app/services/video_processor.py` (FFmpeg) |
| 4 | First end-to-end: MVP works |
| 5 | `backend/app/services/ocr_detector.py`, `ml/yolo/` |
| 6 | `backend/app/services/audio_detector.py`, `subtitle_gen.py` |
| 7 | `backend/app/services/highlight_ranker.py`, `viral_scorer.py` |
| 8 | `frontend/components/timeline-editor.tsx`, vertical reframe |
| 9 | UI polish across `frontend/components/` |
| 10 | `desktop/src-tauri/` (Tauri packaging), `scripts/` |
| 11 | Bug fixes from user testing |
| 12 | Docs polish: README, blog posts, `docs/final-retro.md` |

---

## Tips for Working with This Structure

1. **Don't put generated files in version control** — `.gitignore` handles this. If you see `__pycache__/`, `node_modules/`, or videos appearing in `git status`, something's wrong.

2. **One concept = one file** — when `tasks.py` in routes grows past 200 lines, split it.

3. **`services/` is for verbs, `models/` is for nouns** — `video_processor.py` (verb: process) vs `task.py` (noun: a task).

4. **Tests live next to code** — `backend/tests/test_X.py` mirrors `backend/app/services/X.py`.

5. **Daily logs are your future self's gift** — even a 3-line `weekly/day-XX.md` is worth writing.