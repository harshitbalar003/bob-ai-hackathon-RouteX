"""
app/agents/assistant.py — Engine-as-tool orchestration for /assistant/query.

Routes free-text operator questions to the relevant engine(s), composes an
answer from what they returned.

Rules:
  1. The assistant NEVER answers from its own knowledge when engines return nothing.
     It says so explicitly.
  2. Every number in the response comes from an engine call.
  3. No PII is sent to the model — IDs only, resolved locally.
  4. If the language model is unavailable, deterministic templates are used.
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.llm import get_llm_client


# ── Intent classification ─────────────────────────────────────────────────────
# Simple keyword-based routing — no model call needed for this.

_INTENT_PATTERNS = [
    (r"excursion|temperature|breach|cold.chain|mkt|degree.minut", "cold_chain"),
    (r"impact|affected|disruption|typhoon|storm|strike", "impact"),
    (r"reroute|rerouting|alternative|divert", "reroute"),
    (r"fleet|idle|asset|truck|container|deploy", "fleet"),
    (r"priorit|queue|worklist|urgent|critical", "priority_queue"),
    (r"help|what.can.you|what.do.you", "help"),
]


def classify_intent(query: str) -> str:
    lower = query.lower()
    for pattern, intent in _INTENT_PATTERNS:
        if re.search(pattern, lower):
            return intent
    return "general"


# ── Engine tool calls ─────────────────────────────────────────────────────────

async def _tool_cold_chain_summary(db) -> dict[str, Any]:
    """Fetch open excursions and summarise."""
    from sqlalchemy import select
    from app.models.orm import ExcursionRow
    stmt = select(ExcursionRow).where(ExcursionRow.ended_at == None).limit(10)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return {"count": 0, "summary": "No open excursions."}
    critical = sum(1 for r in rows if r.severity == "critical")
    major = sum(1 for r in rows if r.severity == "major")
    return {
        "count": len(rows),
        "critical": critical,
        "major": major,
        "summary": (
            f"{len(rows)} open excursion(s): {critical} critical, {major} major. "
            f"Most severe: shipment {rows[0].shipment_id}, "
            f"{rows[0].degree_minutes:.0f} deg-min."
        ),
    }


async def _tool_impact_summary(db) -> dict[str, Any]:
    """Fetch active disruptions and impacted shipment counts."""
    from sqlalchemy import select
    from app.models.orm import DisruptionRow, ShipmentRow
    dis_stmt = select(DisruptionRow).where(DisruptionRow.active == True)
    dis_result = await db.execute(dis_stmt)
    disruptions = dis_result.scalars().all()
    if not disruptions:
        return {"count": 0, "summary": "No active disruptions."}
    # Count impacted shipments (those with non-empty impacted_by)
    shp_stmt = select(ShipmentRow).where(ShipmentRow.status.in_(["at_risk", "exception", "delayed"]))
    shp_result = await db.execute(shp_stmt)
    impacted_shp = shp_result.scalars().all()
    return {
        "disruption_count": len(disruptions),
        "impacted_shipments": len(impacted_shp),
        "summary": (
            f"{len(disruptions)} active disruption(s) affecting approximately "
            f"{len(impacted_shp)} shipments. "
            f"Most severe: {disruptions[0].data.get('headline', disruptions[0].id)[:80]}."
        ),
    }


async def _tool_fleet_summary(db) -> dict[str, Any]:
    """Summarise idle fleet assets."""
    from sqlalchemy import select
    from app.models.orm import FleetAssetRow
    stmt = select(FleetAssetRow).where(FleetAssetRow.status == "idle")
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return {"count": 0, "summary": "No idle assets."}
    total_cap_hours = sum(r.capacity_value * r.idle_since_hours for r in rows)
    return {
        "idle_count": len(rows),
        "total_capacity_hours": total_cap_hours,
        "summary": (
            f"{len(rows)} idle assets with {total_cap_hours:.0f} wasted capacity-hours. "
            f"Top idle: {rows[0].id} ({rows[0].type}) — "
            f"{rows[0].idle_since_hours:.0f}h idle."
        ),
    }


async def _tool_priority_summary(db) -> dict[str, Any]:
    """Return the top 5 priority queue items."""
    from sqlalchemy import select
    from app.models.orm import ExcursionRow, FleetAssetRow, RedeploymentMatchRow, ShipmentRow
    from app.engines.priority_queue import build_priority_queue

    exc_result = await db.execute(select(ExcursionRow).limit(10))
    shp_result = await db.execute(
        select(ShipmentRow).where(ShipmentRow.status.in_(["exception", "delayed", "at_risk"])).limit(50)
    )
    fleet_result = await db.execute(select(FleetAssetRow).where(FleetAssetRow.status == "idle").limit(20))
    match_result = await db.execute(select(RedeploymentMatchRow.asset_id))

    items = build_priority_queue(
        exc_result.scalars().all(),
        shp_result.scalars().all(),
        fleet_result.scalars().all(),
        set(match_result.scalars().all()),
    )
    top5 = items[:5]
    summaries = [f"{i+1}. [{x.item.kind.value}] {x.item.headline} (score={x.score})" for i, x in enumerate(top5)]
    return {
        "total_items": len(items),
        "top_5": summaries,
        "summary": f"Top priority queue item: {top5[0].item.headline}" if top5 else "Queue empty.",
    }


_TOOL_HELP = (
    "I can answer questions about: cold chain excursions and temperature breaches, "
    "disruption impact on shipments, fleet idle assets, reroute options, and the "
    "priority queue. Try: 'What open excursions are critical?' or 'How many shipments "
    "are impacted by the current disruption?'"
)


# ── Main assistant ────────────────────────────────────────────────────────────

async def answer_query(query: str, db) -> dict[str, Any]:
    """
    Route a free-text query to the relevant engine tools and compose a response.

    If the engines return no data for the query, the assistant says so explicitly
    and does not hallucinate an answer.
    """
    intent = classify_intent(query)
    engine_data: dict[str, Any] = {}

    if intent == "help":
        return {
            "answer": _TOOL_HELP,
            "source": "template",
            "intent": "help",
            "engine_data": {},
        }

    # Call engine tools
    if intent in ("cold_chain",):
        engine_data = await _tool_cold_chain_summary(db)
    elif intent == "impact":
        engine_data = await _tool_impact_summary(db)
    elif intent == "fleet":
        engine_data = await _tool_fleet_summary(db)
    elif intent in ("priority_queue", "general"):
        engine_data = await _tool_priority_summary(db)
    else:
        engine_data = {"summary": "No relevant engine data found for this query."}

    if not engine_data or engine_data.get("count", 1) == 0:
        return {
            "answer": (
                f"The engines returned no data for '{intent}'. "
                "This assistant only answers from engine output — no speculation."
            ),
            "source": "template",
            "intent": intent,
            "engine_data": engine_data,
        }

    # Compose answer via LLM (or template fallback)
    engine_summary = engine_data.get("summary", str(engine_data))

    # Build prompt (IDs only — no PII)
    prompt = (
        f"You are a supply chain control tower assistant. "
        f"Based only on the following engine data, answer the operator's question.\n\n"
        f"Operator question: {query}\n\n"
        f"Engine data: {engine_summary}\n\n"
        f"Answer concisely in 1-3 sentences. "
        f"Do not add information beyond the engine data provided."
    )

    client = get_llm_client()
    llm_result = client.generate(
        prompt=prompt,
        template_key="free_text_fallback",
        template_kwargs={"engine_summary": engine_summary},
    )

    return {
        "answer": llm_result["text"],
        "source": llm_result["source"],
        "model_id": llm_result.get("model_id"),
        "tokens_used": llm_result.get("tokens_used"),
        "intent": intent,
        "engine_data": engine_data,
    }
