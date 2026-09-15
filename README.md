# RouteX — Supply Chain Control Tower

> Disruption response, cold-chain compliance, and fleet optimisation for pharmaceutical logistics — in a single operator dashboard.

---

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | RouteX |
| **Track** | AI |
| **Project** | Supply Chain Disruption Assistant & Fleet Utilisation Optimizer |

---

## 🎯 Problem Statement

A control-tower operator managing 100–300 active pharmaceutical shipments must simultaneously
answer four questions when an incident fires: which shipments are hit by the disruption, what
rerouting options maintain cold-chain continuity, which fleet assets are idle and deployable, and
whether any temperature excursion is still actionable. Today this takes 30–60 minutes per incident
across 3–5 disconnected systems; RouteX answers all four questions in seconds from a single screen.

---

## 💡 Solution

RouteX is a two-tier operator dashboard: a React 19 SPA with six specialist views backed by a
FastAPI async API running five deterministic decision engines (ColdChain, Impact, Rerouting, Fleet,
PriorityQueue). An optional watsonx.ai Granite 13b layer translates engine output into
natural-language responses via a `/assistant/query` endpoint. The entire system runs from a clean
clone with no `.env` file and no Docker — one seed command, one `npm run dev`.

---

## ✨ Key Features

- **Disruption Impact Scoring:** Haversine + polygon intersection engine scores every active shipment leg against the disruption's geographic area. Only incomplete legs within the active time window are flagged. Each score carries a `Decision` audit trail with formula, threshold, and timestamp.
- **Cold-Chain Excursion Detection:** Deterministic pipeline — gap detection, degree-minute accumulation, MKT (USP \<1079\> formula), first-match regulatory classification (GDP / WHO PQS / USP \<1079\> / FSMA), and a `detectedBeforeDelivery` actionability flag. Every excursion includes its regulatory citation (e.g. "GDP Annex 5.5").
- **Reroute Comparison with Cold-Chain Continuity:** Lane-graph rerouting engine generates alternatives that avoid the disruption's affected nodes and checks reefer continuity. A route that spoils cargo is never presented as valid. The null option always participates in the ranking.
- **Fleet Redeployment Matching:** Idle assets ranked by wasted capacity-hours; matched to impacted cold-chain shipments by proximity and reefer capability.
- **Unified Priority Queue:** Excursions, shipment exceptions, and idle assets merged into a single weighted worklist — the operator always sees the most urgent action first.
- **Natural-Language Assistant:** `POST /api/v1/assistant/query` — intent classification → engine tool call → watsonx.ai Granite answer or deterministic template fallback. The assistant never answers from its own knowledge when engines return no data.
- **Mock / API dual mode:** `VITE_DATA_SOURCE=mock` (default) runs fully offline from fixture JSON. `VITE_DATA_SOURCE=api` switches to the live backend. Both modes render identical screens.

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Languages** | Python 3.11+, TypeScript 6 |
| **Frameworks** | FastAPI 0.111, React 19, Vite 8 |
| **IBM Technologies** | watsonx.ai (`ibm/granite-13b-instruct-v2`) via `ibm-watsonx-ai` Python SDK |
| **Data / State** | TanStack Query 5, Zustand 5, pydantic v2, SQLAlchemy 2 async |
| **Database** | SQLite + aiosqlite (PostgreSQL-ready via env var) |
| **Visualisation** | d3-geo + topojson (world map), Recharts 3 (temperature trace, utilisation chart) |
| **Styling** | Tailwind CSS 3 with custom design tokens (IBM Plex Sans, deep-navy palette) |
| **Testing** | Vitest 5 + Testing Library (frontend), pytest + pytest-asyncio (backend) |
| **Other** | Alembic (migrations), openapi-typescript (type generation), oxlint |

---

## 📁 Repository Structure

```
bob-ai-hackathon-RouteX/
├── submission.yaml               ← Structured submission metadata
├── README.md                     ← This file
│
├── src/
│   ├── .env.example              ← All environment variables with defaults
│   ├── backend/
│   │   ├── app/
│   │   │   ├── agents/           ← assistant.py, llm.py (watsonx.ai client)
│   │   │   ├── engines/          ← cold_chain.py, impact.py, rerouting.py, fleet.py, priority_queue.py
│   │   │   ├── models/           ← domain.py (pydantic), orm.py (SQLAlchemy)
│   │   │   ├── routers/          ← 8 FastAPI routers
│   │   │   ├── rules/            ← gdp.yaml, who_pqs.yaml, usp_1079.yaml, fsma.yaml
│   │   │   ├── seed/             ← deterministic data generator
│   │   │   └── simulation/       ← replay.py (TYPHOON_VACCINE demo scenario)
│   │   ├── requirements.txt
│   │   └── tests/                ← pytest test suite
│   └── frontend/
│       └── src/
│           ├── components/       ← UI primitives + feature components
│           ├── lib/
│           │   ├── adapter/      ← mock.ts, api.ts, types.ts
│           │   ├── queries.ts    ← TanStack Query hooks
│           │   └── store.ts      ← Zustand UI state
│           ├── pages/            ← 6 route pages
│           └── types/            ← domain.ts, api.generated.ts
│
├── docs/
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   ├── setup-guide.md
│   └── data-sources.md
│
├── demo/                         ← screenshots, video link, live demo URL
└── presentation/                 ← slide deck
```

---

## ⚡ How to Run

### Quick start (one command)

```bash
bash scripts/verify.sh
```

Installs dependencies, seeds the database, starts the API, verifies all endpoints, and builds the
frontend. Exit 0 = everything working.

### Manual — frontend only (no backend needed)

```bash
# Step 1 — seed fixture files (run once)
cd src/backend
pip install -r requirements.txt
python -m app.seed --seed 42

# Step 2 — run the frontend in mock mode
cd src/frontend
npm install
npm run dev        # → http://localhost:5173  (shows MOCK · stubbed auth indicator)
```

> **Demo account** (seeded automatically): `demo@coldfront.app` / `demo-control-tower`
> Click **Enter demo** on the landing page — one click to the control tower.

### Manual — full stack (frontend + live API)

```bash
# Terminal 1 — backend
cd src/backend
pip install -r requirements.txt
python -m app.seed --seed 42
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs

# Terminal 2 — frontend (API mode)
cd src/frontend
npm install
VITE_DATA_SOURCE=api npm run dev   # → http://localhost:5173  (shows API indicator)
```

### Tests

```bash
# Backend
cd src/backend && pytest tests/ -v

# Frontend
cd src/frontend && npm test
```

---

## 🖥️ Demo

| Artifact | Link |
|---|---|
| 📹 Demo Video | [See demo/demo-video-link.txt](demo/demo-video-link.txt) |
| 🌐 Live Demo | [See demo/live-demo-url.txt](demo/live-demo-url.txt) |
| 🖼️ Screenshots | [See demo/screenshots/](demo/screenshots/) |
| 📊 Presentation | [See presentation/](presentation/) |

---

## ⚠️ Known Limitations

- **watsonx.ai is optional:** The assistant endpoint works fully without an API key via deterministic template fallback. Natural-language quality improves with `WATSONX_ENABLED=true`.
- **SQLite, not PostgreSQL:** Production-grade databases require only changing `DATABASE_URL` — the async SQLAlchemy setup already supports PostgreSQL.
- **SSE stream is disabled by default:** Set `FEATURE_SSE=true` to enable the real-time event stream. The priority queue supports `?since=` polling as an alternative.
- **Lane network is representative, not complete:** The rerouting engine's lane graph covers the major global nodes used in the scripted scenarios; it is not a comprehensive freight network.
- **Authentication is present but not hardened:** Passwords are hashed with bcrypt (cost 12), session tokens are stored in httpOnly SameSite=Lax cookies, and a demo account is seeded automatically. This is not production-hardened — there is no email verification, no password reset, no account lockout beyond rate limiting, and CORS remains open. Demo credentials: `demo@coldfront.app` / `demo-control-tower`.
- **CORS is fully open:** `allow_origins=["*"]` must be tightened before any public deployment.

---

## 🏅 What We're Most Proud Of

**The cold-chain excursion engine and its audit trail.** The full pipeline — gap detection,
degree-minute accumulation, USP \<1079\> MKT formula, first-match regulatory classification across
four real rule packs (GDP, WHO PQS, USP \<1079\>, FSMA), and the `detectedBeforeDelivery`
actionability flag — is entirely deterministic, unit-tested, and produces a verifiable `Decision`
object per excursion. This is the kind of pharmaceutical-grade traceability that regulatory auditors
actually need, and it runs with zero external dependencies.

The **dual-mode adapter architecture** is a close second: evaluators can explore the complete
six-route UI with no backend at all, and operators in the field can switch to live API data by
changing a single environment variable.
