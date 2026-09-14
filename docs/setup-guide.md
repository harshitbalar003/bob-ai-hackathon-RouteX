# Setup Guide

> **This file is read by the automated evaluation pipeline. Be precise and complete.**

## Prerequisites

- Python 3.11 or later (`python --version`)
- Node.js 18 or later (`node --version`)
- No Docker, no cloud account, no `.env` file required.

## Quick start (one command)

```bash
bash scripts/verify.sh
```

This script: installs dependencies, seeds the database, starts the API, verifies
all endpoints, regenerates TypeScript types, and builds the frontend. If it exits
0, everything is working.

---

## Manual step-by-step

### 1 — Backend setup

```bash
cd src/backend
pip install -r requirements.txt
```

### 2 — Seed the database (deterministic, < 15 seconds)

```bash
# From src/backend/
python -m app.seed --seed 42
```

This generates the full synthetic dataset, seeds the SQLite database
(`src/backend/supply_chain.db`), and writes fixture files to
`src/frontend/src/data/fixtures/` so both the mock adapter and the API
adapter show identical data.

Run it twice with the same seed — you get a byte-identical database.

### 3 — Start the API server

```bash
# From src/backend/
uvicorn app.main:app --reload --port 8000
```

API docs available at http://localhost:8000/docs  
Health check: http://localhost:8000/api/v1/health

### 4 — Frontend setup

```bash
cd src/frontend
npm install
```

### 5 — Run the frontend (mock mode — no backend needed)

```bash
# From src/frontend/
npm run dev
```

Opens at http://localhost:5173 using the fixture data written in step 2.
The data mode indicator in the bottom-right corner shows `MOCK`.

### 6 — Run the frontend against the live API

```bash
# With the backend running in another terminal:
VITE_DATA_SOURCE=api npm run dev
```

The indicator changes to `API`. Both modes render identical screens because
the fixtures were exported from the same database.

---

## Running tests

### Backend

```bash
cd src/backend
pytest tests/ -v
```

### Frontend

```bash
cd src/frontend
npm test
```

---

## Regenerating TypeScript types from the live OpenAPI schema

```bash
# Requires the backend to be running on :8000
cd src/frontend
npm run generate:types
```

This writes `src/types/api.generated.ts`. The committed file must match — if it
differs, the backend contract has drifted from the frontend types.

---

## Running migrations (optional — seed handles this automatically)

```bash
cd src/backend
python -m alembic upgrade head
```

---

## Environment variables

No `.env` file is required for local development. All defaults work out of the box.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./supply_chain.db` | SQLite, file-based, no server |
| `VITE_DATA_SOURCE` | `mock` | Set to `api` to use the live backend |
| `VITE_API_BASE_URL` | `/api` | Proxied to `:8000` by Vite dev server |
| `WATSONX_ENABLED` | `false` | Set to `true` + provide API key for LLM features |

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError: app` | Run commands from `src/backend/`, not from repo root |
| `aiosqlite` not found | `pip install -r requirements.txt` |
| Port 8000 already in use | `uvicorn app.main:app --port 8001` and set `VITE_API_BASE_URL=http://localhost:8001/api` |
| Blank screens in mock mode | Run `python -m app.seed --seed 42` to regenerate fixture files |
| TypeScript build errors | Run `npm run generate:types` — the generated types may be stale |
| Backend returns 500 on excursions | Fixture data was loaded without running the seed; run `python -m app.seed --seed 42` |
