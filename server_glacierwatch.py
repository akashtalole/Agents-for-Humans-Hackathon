"""GlacierWatch FastAPI + React web UI server entrypoint.

Run with:  python server_glacierwatch.py
(or, in production, the Dockerfile.glacierwatch.webapp image's CMD does this)

Serves the JSON API under /api/* (see glacierwatch/api.py) and, once built,
the React frontend (webapp/glacierwatch/dist/) from /.
"""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("glacierwatch.api:app", host="0.0.0.0", port=8000)
