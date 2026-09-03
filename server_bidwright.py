"""BidWright FastAPI web UI. Run with: python server_bidwright.py, or: uvicorn bidwright.api:app --reload"""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("bidwright.api:app", host="0.0.0.0", port=8000)
