# GlacierWatch web UI (frontend)

Vite + React + TypeScript + Tailwind CSS frontend for GlacierWatch's web UI.
Talks to the FastAPI backend in `glacierwatch/api.py` — see `../../GLACIERWATCH.md`'s
"Web UI" section for the full architecture and how to run the whole thing
(backend + frontend) locally or deploy it to AWS.

## Local development

```bash
npm install
npm run dev
```

`vite.config.ts` proxies `/api/*` to `http://localhost:8000`, so also run
the backend in another terminal:

```bash
# from the repo root
pip install -e ".[api]"
python server_glacierwatch.py
```

## Build

```bash
npm run build
```

Outputs to `dist/`, which `glacierwatch/api.py` serves at `/` when present
(mounted after all `/api/*` routes, so the API always takes priority).
`dist/` and `node_modules/` are gitignored — built fresh by `npm run build`
or by `Dockerfile.glacierwatch.webapp`'s frontend build stage.

## Structure

```
src/
  api.ts                        Typed fetch wrappers + the SSE activity-log helper
  types.ts                      TypeScript types matching glacierwatch/api.py's response shapes
  hooks/useTheme.ts             Light/dark mode, persisted in localStorage
  components/
    Header.tsx                   Title, tagline, model-status pill, theme toggle
    DisclaimerBanner.tsx         Always-visible non-prediction disclaimer (from GET /api/status)
    RunPanel.tsx                 "Run GlacierWatch" button + live activity log
    StatusBadgeBanner.tsx        error/warning/success banner after a run completes
    ResultsTabs.tsx               The four result tabs, matching app_glacierwatch.py exactly
  App.tsx                        Ties it all together
```
