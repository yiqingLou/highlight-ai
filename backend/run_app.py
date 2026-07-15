"""Packaged entry point: start the API + frontend server.

PyInstaller needs a real script (not the uvicorn CLI). No --reload here:
reload is a dev feature and breaks under a frozen build.
"""
import uvicorn

from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
