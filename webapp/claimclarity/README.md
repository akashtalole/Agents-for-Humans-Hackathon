# ClaimClarity web frontend

Vite + React + TypeScript + Tailwind CSS. Talks to the FastAPI backend in
`claimclarity/api.py` (see the repo root `CLAIMCLARITY.md`'s "Web UI"
section for the full architecture).

```bash
npm install
npm run dev      # local dev server, proxies /api to http://localhost:8000
npm run build    # production build -> dist/ (served by the FastAPI app)
```

Run the backend separately for `npm run dev` to have something to talk to:

```bash
# from the repo root, in another terminal
pip install -e ".[api]"
python3 server_claimclarity.py
```
