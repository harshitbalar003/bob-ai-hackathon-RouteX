# Solution Overview

## What We Built

**RouteX** is a supply chain control-tower operator dashboard for pharmaceutical and
temperature-sensitive logistics. It gives a single operator a unified, real-time view of
disruptions, cold-chain excursions, rerouting options, and idle fleet assets — answering the four
critical questions described in [`problem-statement.md`](problem-statement.md) in seconds instead
of hours.

The system is a React 19 single-page application backed by a FastAPI async API, with five
deterministic decision engines running against a SQLite database seeded from synthetic but
physically plausible data. An optional watsonx.ai Granite language layer translates engine output
into natural-language operator responses via a `/assistant/query` endpoint.

---

## How It Works

1. **Seed once, run anywhere.** Running `python -m app.seed --seed 42` generates 120 shipments,
   3 concurrent disruptions, 40 fleet assets, ~27,000 sensor readings, and all derived artefacts
   (excursions, reroute options, redeployment matches). The same seed always produces the same
   byte-identical database. The seed also exports JSON fixture files to the frontend so the
   app works in mock mode with zero backend dependency.

2. **Disruption impact scoring.** When the operator opens a disruption (e.g. Typhoon Krathon at
   Shanghai), the Impact Engine computes which shipment legs intersect the disruption's geographic
   area using haversine distance for circular zones and point-in-polygon for polygon zones. Only
   incomplete legs within the disruption's active time window are scored — completed legs are never
   flagged, eliminating noise. Each result carries a `Decision` object with the scoring formula,
   threshold, and timestamp.

3. **Rerouting with cold-chain continuity.** The Rerouting Engine models the network as a weighted
   lane graph. For each impacted shipment, it searches for paths that avoid the disruption's
   affected nodes, respects modal constraints, and checks whether the proposed detour keeps the
   cargo within its stable temperature window. A route that saves two days but spoils a vaccine
   batch is never presented as a valid option. The null option ("accept the delay") is always
   included and wins if it genuinely scores better than all alternatives.

4. **Fleet redeployment matching.** The Fleet Engine identifies all idle assets and ranks them by
   wasted capacity-hours. The Redeployment Engine then matches idle reefer trucks to impacted
   cold-chain shipments by proximity and capability, producing a shortlist the operator can act on
   in a single call.

5. **Cold-chain excursion detection.** The ColdChain Engine processes sensor time series through a
   deterministic pipeline: clean → gap-detect → detect out-of-range runs (10-minute debounce) →
   compute degree-minutes and MKT (USP <1079> formula) → classify against the active regulatory
   rule pack (GDP / WHO PQS / USP <1079> / FSMA). Each excursion is classified as
   informational / minor / major / critical with a full audit trail, a regulatory citation, and an
   actionability flag (`detectedBeforeDelivery`).

6. **Priority queue.** All three item types (excursions, shipment exceptions, idle assets) feed a
   single ranked worklist with a transparent weighted score so the operator always sees the most
   urgent action first.

7. **Natural-language assistant.** The operator can ask free-text questions. The assistant
   classifies intent (regex, no model call), runs the relevant engine tool against the live
   database, and passes the grounded engine output to `ibm/granite-13b-instruct-v2` for a concise
   natural-language answer. If watsonx.ai is unavailable, deterministic templates produce an equally
   accurate (if less fluent) response — the system never degrades silently.

---

## Architecture Diagram

> See [`architecture.md`](architecture.md) for the detailed diagram and component table.

```
[Operator] → [React SPA — 6 routes]
                    ↓  mock adapter (fixture JSON)
                    ↓  api adapter (REST)
             [FastAPI /api/v1]
                    ↓
        ┌──────────────────────────┐
        │  ColdChain Engine        │  degree-minutes, MKT, GDP classification
        │  Impact Engine           │  haversine + polygon intersection
        │  Rerouting Engine        │  lane graph, cold-chain continuity check
        │  Fleet Engine            │  idle ranking, redeployment matching
        │  Priority Queue Engine   │  merged weighted worklist
        └──────────────────────────┘
                    ↓
             [SQLite DB]   ←   [app/seed — deterministic generator]
                    ↓
        [Assistant Agent] → [watsonx.ai Granite 13b] or [Template fallback]
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Deterministic engines — no model calls for scoring** | Every number the operator sees comes from a pure Python function with no randomness and no network call. Reproducibility and auditability are non-negotiable in pharmaceutical logistics. |
| **Adapter pattern (mock / api)** | Frontend components never call `fetch` directly. Switching `VITE_DATA_SOURCE=api` is a one-line change; mock mode works on a plane with no internet. Judges can evaluate the full UI without running the backend. |
| **watsonx.ai as explainer, not decision-maker** | The LLM translates engine output into plain language. It never originates a number, a severity classification, or a routing decision. If it fails, templates cover 100% of the response surface. |
| **SQLite for the hackathon, SQLAlchemy async for production** | Zero-install, byte-identical across machines (same seed), no Docker dependency. The `DATABASE_URL` is a single env var — swapping to PostgreSQL requires no code change. |
| **Regulatory rule packs as YAML** | Compliance thresholds (GDP, WHO PQS, USP <1079>, FSMA) live in versioned YAML files, not in code. A compliance officer can update a threshold without touching Python. |
| **Severity as colour + shape + text + regulatory citation** | Never colour alone. Every severity display includes the shape glyph (●■▲◆), the text label, the numeric driver, and the regulatory rule that triggered it. Accessibility and audit requirements both demand this. |
| **`detectedBeforeDelivery` flag on excursions** | This single boolean is the most operationally important field. An excursion detected before delivery is still actionable (reroute, repackage, escalate to carrier). After delivery it becomes a batch disposition problem. The priority queue weights this heavily. |
| **Confidence field on disruptions** | dis-003 (A2 congestion) has 55% confidence. The UI shows "Low confidence (55%)" and the assistant uses the same signal to hedge its answer. Uncertain data is never presented as settled fact. |

---

## IBM Technologies Used

### watsonx.ai — `ibm/granite-13b-instruct-v2`

Used in `app/agents/llm.py` as the natural-language layer of the assistant endpoint
(`POST /api/v1/assistant/query`). When `WATSONX_ENABLED=true` and credentials are provided:

- The `ibm_watsonx_ai.foundation_models.ModelInference` client is initialised with `decoding_method="greedy"` and `temperature=0.0` to ensure deterministic responses.
- Engine data (never raw PII — only IDs and aggregated numbers) is passed in a structured prompt.
- The model generates a 1–3 sentence operator-facing answer grounded in the engine output.
- Token usage is logged per call and returned in the API response for cost tracking.

The integration is gracefully degraded: if the `ibm-watsonx-ai` package is not installed, or if
the API key is absent, or if the network call fails, the `LLMClient` automatically falls back to
a deterministic template from `_TEMPLATES` that produces a fully accurate (if less fluent)
response. This means watsonx.ai is additive — the core system is complete without it.

**Excluded models (per hackathon rules):** `llama-3-405b-instruct`, `mistral-medium-2502`,
`mistral-small-3-1-24b-instruct-2503`.

---

## User Experience Overview

The operator opens the **Control Tower** (`/`) and sees:
- A disruption band showing active events with severity, confidence, and impacted shipment count.
- A d3-geo SVG world map with disruption zones, active shipment routes, and fleet asset markers.
- A priority queue listing the top actions ranked by the weighted engine score.

Clicking a disruption opens **Disruption Detail** (`/disruptions/:id`) with an impact table showing
every affected shipment scored by delay, value, cold-chain exposure, and cascade risk.

Clicking a shipment opens **Shipment Detail** (`/shipments/:id`) with a leg timeline, the sensor
temperature trace (Recharts area chart), and the three best reroute options with a side-by-side
cost/delay/cold-chain comparison.

The **Cold-Chain Monitor** (`/cold-chain`) shows all open excursions ranked by severity with
degree-minutes, MKT, regulatory citation (e.g. "GDP Annex 5.5"), and the actionability flag.

The **Fleet Page** (`/fleet`) shows idle asset utilisation and redeployment match candidates.

All timestamps are rendered in the operator's local timezone with a zone label. All numerals use
tabular-lining figures for scannable alignment in tables.
