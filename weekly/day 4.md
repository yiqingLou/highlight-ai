# Day 4 · 2026-05-21 Thursday

## Done today

- Installed pyenv-win, used it to install Python 3.11.9 alongside existing 3.14.2
- Set Python 3.11.9 as the project default via pyenv local
- Installed nvm-windows, used it to install Node.js 20.20.2 alongside existing 24
- Installed FFmpeg 8.1.1 full build (with NVENC/CUDA/Whisper support — perfect for RTX 4090)
- Hello World verified for all three tools (Python, Node, FFmpeg generated test video at 59x speed)
- Created Python virtual environment in backend/, installed FastAPI + uvicorn
- Wrote minimal FastAPI scaffold (root + /api/hello endpoints)
- Verified FastAPI runs at localhost:8000, /docs auto-generates Swagger UI
- Deleted empty frontend folder, recreated with `create-next-app` (TypeScript + Tailwind + App Router)
- Verified Next.js dev server runs at localhost:3000

## Reflections

- nvm-windows installed to AppData\Local\nvm (not the default Roaming) — required manual PATH setup
- pyenv-win install script doesn't always refresh PATH automatically — fixed with `[System.Environment]::SetEnvironmentVariable(...)` calls
- FFmpeg's full build with --enable-nvenc --enable-cuda-llvm --enable-whisper means Week 6 subtitle generation will be much simpler
- FastAPI's auto-generated /docs is impressive — Python docstrings automatically become API documentation
- Total environment setup time was much faster than expected (~30 min instead of 2-3 hours) — RTX 4090 + good network helped

## Day 5 plan (2026-05-22 Friday)

- FFmpeg performance benchmark: process a real game recording, measure speed with and without GPU acceleration
- Wrap up Week 1 with retrospective
- Optionally start drafting Week 2 backend structure

## Mood

Big day. The project transitioned from "documentation" to "running code." Two servers are alive on my machine now (FastAPI + Next.js). Tomorrow's FFmpeg benchmark is the critical Week 1 milestone — if GPU acceleration works well, the project's performance story is locked in.