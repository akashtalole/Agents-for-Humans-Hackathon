"""ClaimClarity FastAPI + React web UI entrypoint.

Run with:  python3 server_claimclarity.py
(after `pip install -e ".[api]"` and, for local dev, building the frontend
with `cd webapp/claimclarity && npm install && npm run build` - or run the
frontend separately with `npm run dev`, which proxies /api to this server.)

See CLAIMCLARITY.md's "Web UI" section for the full architecture.
"""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("claimclarity.api:app", host="0.0.0.0", port=8000)
