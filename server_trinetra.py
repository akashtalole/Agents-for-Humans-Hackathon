"""Trinetra FastAPI + React web UI. Run with: python server_trinetra.py, or: uvicorn trinetra.api:app --reload"""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("trinetra.api:app", host="0.0.0.0", port=8000)
