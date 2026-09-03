# BidWright web UI

React + TypeScript + Tailwind CSS frontend for BidWright, served by the
FastAPI backend in `bidwright/api.py`. See `BIDWRIGHT.md`'s "Web UI" section
for the full architecture and how to run the whole stack locally.

```bash
npm install
npm run dev      # dev server on :5173, proxies /api to localhost:8000
npm run build    # outputs dist/, served by the FastAPI app in production
```
