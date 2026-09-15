# Architecture

## System Architecture

RouteX is a **three-layer application**:

1. **Deterministic engines** (`app/engines/`) — classify excursion severity, score disruption impact, rank reroutes and fleet assets. Every verdict carries a `Decision` audit trail. These never change.
2. **Language layer** (`app/agents/`) — explains engine output via watsonx.ai Granite or a deterministic template fallback. Optional.
3. **Predictive layer** (`app/ml/`) — forecasts future states (P(breach within 4h)). Parallel to the engines, never inside them. Disabled by default (`ML_ENABLED=false`); the system is fully functional without it.

The frontend is a React 19 SPA communicating over REST with the FastAPI backend. All data is sourced from a local SQLite database seeded deterministically at startup.

**Three-layer separation guarantee:** The ML layer may never classify excursion severity, assign a regulatory citation, decide a disposition, or produce any value that a `Decision` record depends on. Severity classification stays in `app/engines/cold_chain.py` against the YAML rule packs.

```mermaid
graph TD
    subgraph Browser
        A[Operator / Browser]
        FE[Frontend — React 19 + Vite]
        A --> FE
    end

    subgraph Backend — FastAPI + Python
        API[REST API /api/v1]

        subgraph Layer1 [Layer 1 — Deterministic Engines]
            ENG_CC[ColdChain Engine — classifies severity]
            ENG_IMP[Impact Engine]
            ENG_RR[Rerouting Engine]
            ENG_FL[Fleet Engine]
            ENG_PQ[Priority Queue Engine]
        end

        subgraph Layer2 [Layer 2 — Language]
            AG[Assistant Agent]
            LLM[LLM Client — watsonx.ai]
            TPL[Template Fallback]
        end

        subgraph Layer3 [Layer 3 — Predictive ML — app/ml/]
            ML_REG[Registry — loads artifacts]
            ML_FEAT[features.py — shared train+serve]
            ML_PRED[Excursion Forecaster]
            ML_BATCH[Batch Forecaster]
            DB_PRED[(predictions table)]
        end

        DB[(SQLite — supply_chain.db)]
        SSE[SSE Stream /events]

        API --> ENG_CC
        API --> ENG_IMP
        API --> ENG_RR
        API --> ENG_FL
        API --> ENG_PQ
        API --> AG
        AG --> LLM
        LLM -->|WATSONX_ENABLED=false| TPL
        API --> DB
        API --> SSE
        ML_REG --> ML_PRED
        ML_FEAT --> ML_PRED
        ML_BATCH --> ML_PRED
        ML_BATCH --> DB_PRED
        API --> ML_BATCH
        API --> DB_PRED
        ENG_PQ -.->|optional prediction_rows| ML_PRED
    end

    subgraph IBM Cloud — Optional
        WX[watsonx.ai — ibm/granite-13b-instruct-v2]
        LLM -->|WATSONX_ENABLED=true| WX
    end

    FE -->|Mock adapter — no network| FE
    FE -->|API adapter — REST| API
```

---

## Components

| Component | Technology | Responsibility |
|---|---|---|
| **Frontend SPA** | React 19, TypeScript, Vite 8, Tailwind CSS 3 | Six-route operator dashboard: Control Tower, Disruption Detail, Shipment Detail, Reroute Workbench, Cold-Chain Monitor, Fleet Page |
| **Data Adapter** | TypeScript adapter pattern (mock / api) | Decouples components from data source; switches between fixture JSON (mock) and live REST (api) via `VITE_DATA_SOURCE` |
| **State Management** | Zustand 5 | UI selections (active disruption, active shipment), map layer toggles |
| **Data Fetching** | TanStack Query 5 | Query hooks wrapping the DataAdapter; handles caching, loading, and error state |
| **Map** | d3-geo + topojson + world-atlas | SVG world map with disruption zones, shipment route overlays, and fleet asset markers |
| **Charts** | Recharts 3 | Temperature trace, fleet utilisation area chart |
| **Backend API** | FastAPI 0.111, Python 3.11+, pydantic v2 | REST API — 8 routers; async SQLAlchemy with aiosqlite |
| **Decision Engines** | Pure Python (no external deps) | Five deterministic engines: ColdChain, Impact, Rerouting, Fleet, PriorityQueue |
| **Assistant Agent** | `app/agents/assistant.py` | Intent classification → engine tool calls → LLM or template composition |
| **LLM Client** | `ibm-watsonx-ai` (optional) | Wraps `ibm/granite-13b-instruct-v2`; falls back to deterministic templates when unavailable |
| **Predictive ML Layer** | `app/ml/` — `scikit-learn==1.5.2` only | Model 1 (Excursion Forecaster): P(breach within 4h), calibrated probability, batch serving. Disabled by default (`ML_ENABLED=false`). Never classifies severity. |
| **Database** | SQLite + aiosqlite + SQLAlchemy 2 | File-based, no server; seeded deterministically via `python -m app.seed --seed 42` |
| **Seed / Fixtures** | `app/seed/` + `app/export_fixtures.py` | Generates all synthetic data, seeds the DB, and exports JSON fixtures to the frontend |
| **Simulation Harness** | `app/simulation/replay.py` | Clock-driven replay of the scripted TYPHOON_VACCINE scenario for demo |
| **Rule Packs** | YAML files in `app/rules/` | GDP, WHO PQS, USP <1079>, FSMA thresholds driving cold-chain classification |

---

## API Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/disruptions` | List active disruptions (filterable by severity, type) |
| `GET` | `/api/v1/disruptions/{id}` | Single disruption |
| `GET` | `/api/v1/disruptions/{id}/impact` | Shipment impact scores for a disruption |
| `GET` | `/api/v1/shipments` | List shipments (filterable by status, cold-chain) |
| `GET` | `/api/v1/shipments/{id}` | Single shipment with legs and telemetry |
| `GET` | `/api/v1/shipments/{id}/reroutes` | Reroute options for a shipment |
| `GET` | `/api/v1/cold-chain/excursions` | Excursion list (filterable by severity, open/closed) |
| `GET` | `/api/v1/cold-chain/sensor-readings/{shipment_id}` | Sensor time series for a shipment |
| `GET` | `/api/v1/fleet/assets` | Fleet assets (filterable by status) |
| `GET` | `/api/v1/fleet/redeployment-matches` | Idle asset → impacted shipment redeployment matches |
| `GET` | `/api/v1/priority-queue` | Ranked operator worklist (excursions + exceptions + idle assets) |
| `POST` | `/api/v1/assistant/query` | Natural-language query → engine-grounded answer |
| `GET` | `/api/v1/stream/events` | SSE stream (gated behind `FEATURE_SSE=true`) |

---

## Data Flow

### Normal operator session (mock mode — no backend required)

1. Operator opens `http://localhost:5173`; Vite serves the React SPA.
2. The `DataAdapter` is initialised as the **mock adapter** (default `VITE_DATA_SOURCE=mock`).
3. TanStack Query hooks (`useDisruptions`, `useShipments`, etc.) call the mock adapter which reads directly from the JSON fixture files in `src/data/fixtures/`.
4. Components receive typed domain objects and render immediately — no network latency.

### API mode (live backend)

1. `VITE_DATA_SOURCE=api` switches the adapter to the **API adapter**.
2. The Vite dev server proxies `/api` → `http://localhost:8000/api`.
3. The API adapter calls the FastAPI backend; TanStack Query manages caching and re-fetching.
4. Backend routers load rows from SQLite, pass them through the relevant deterministic engine, and return pydantic-serialised domain models.
5. The API adapter deserialises the JSON into the same TypeScript domain types used by the mock adapter — both modes render identical screens.

### Assistant query flow

1. Operator types a free-text question (e.g. "Which cold-chain shipments are critical right now?").
2. `POST /api/v1/assistant/query` is called.
3. `classify_intent()` matches the query to one of: `cold_chain | impact | fleet | priority_queue | reroute | help | general` using regex patterns.
4. The matching engine tool is called against the live database (e.g. `_tool_cold_chain_summary`).
5. Engine data is passed as a grounded prompt to the LLM client.
6. If `WATSONX_ENABLED=true` and credentials are present, `ibm/granite-13b-instruct-v2` generates a natural-language answer. Otherwise a deterministic template fills in the numbers.
7. The response includes `source: "watsonx" | "template"`, token count, intent, and the raw engine data.

### Cold-chain excursion detection pipeline

1. `app/seed/telemetry.py` generates ~4,608 sensor readings per cold-chain shipment at 5-minute intervals using a first-order thermal model.
2. On `python -m app.seed`, readings are written to SQLite and exported to `sensor-readings.json`.
3. The **ColdChain Engine** (`app/engines/cold_chain.py`) cleans the series (sort, dedup, gap detection at `3 × nominal_interval`), detects contiguous out-of-range runs with a 10-minute debounce, computes degree-minutes and MKT (USP <1079> formula), and classifies each excursion against the active rule pack (first-match on severity).
4. Each excursion carries a full `Decision` audit trail (rule, threshold, classification, timestamp).

### Priority queue ranking

1. Three item types feed the queue: `excursion`, `shipment_exception`, `idle_asset`.
2. Each item is scored by a weighted formula (weights in `config.py`):
   - **Excursion**: `0.45 × severity + 0.25 × actionability + 0.20 × value`
   - **Shipment exception**: `0.45 × severity + 0.30 × eta_slip + 0.20 × value`
   - **Idle asset**: `0.55 × wasted_hours + 0.45 × has_match`
3. All three pools are merged and sorted descending. The operator worklist is the top-N items.

---

## Frontend Route Map

| Route | Component | Data hooks used |
|---|---|---|
| `/` | `ControlTower.tsx` | `useDisruptions`, `useShipments`, `useFleetAssets`, `usePriorityQueue` |
| `/disruptions/:id` | `DisruptionDetail.tsx` | `useDisruption`, `useDisruptionImpact` |
| `/shipments/:id` | `ShipmentDetail.tsx` | `useShipment`, `useSensorReadings`, `useRerouteOptions` |
| `/reroutes` | `RerouteWorkbench.tsx` | `useRerouteOptions` |
| `/cold-chain` | `ColdChainMonitor.tsx` | `useExcursions`, `useSensorReadings` |
| `/fleet` | `FleetPage.tsx` | `useFleetAssets`, `useRedeploymentMatches` |

---

## Security Considerations

- API keys (`WATSONX_API_KEY`, `WATSONX_PROJECT_ID`) are loaded via `pydantic-settings` from environment variables — never from committed files. `.env` is in `.gitignore`.
- No real credentials, personal data, or client data exist in the codebase — all data is fully synthetic (see `docs/data-sources.md`).
- CORS is set to `allow_origins=["*"]` for hackathon convenience. In production this must be tightened to the frontend origin.
- The assistant agent passes only shipment/excursion IDs to the LLM — not cargo owner names, consignee details, or any PII.
- The SQLite database is file-local; no network-exposed DB server is required.
- The SSE stream endpoint is disabled by default (`FEATURE_SSE=false`) to reduce attack surface.

---

## Scalability Notes

The hackathon prototype is intentionally simple and stateless in its core engines:

- The **FastAPI backend** is stateless above the database layer and could be horizontally scaled behind a load balancer. The bottleneck is SQLite — replacing the `DATABASE_URL` with a PostgreSQL connection string is a one-line change (SQLAlchemy 2 async is already configured for it).
- The **deterministic engines** (ColdChain, Impact, Rerouting, Fleet, PriorityQueue) are pure functions with no shared state. They can be extracted into separate microservices or run as Cloud Functions without refactoring.
- The **watsonx.ai calls** are the highest-latency operation (~1–3 s). Adding a Redis result cache keyed on `(intent, engine_data_hash)` would eliminate repeated calls for identical queries.
- The **SSE stream** uses an in-memory `asyncio.Queue`. For multi-process deployments, this must be replaced with a Redis pub/sub or similar shared bus.
- The **fixture export** pipeline (`app/export_fixtures.py`) means the frontend mock mode can be served from a CDN with zero backend dependency — useful for demos and evaluation.
