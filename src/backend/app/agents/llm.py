"""
app/agents/llm.py — watsonx.ai wrapper with deterministic template fallback.

The language layer is NEVER load-bearing for a number.
It explains decisions already made by the engines; it never makes them.

If watsonx.ai is unavailable or WATSONX_ENABLED=false, deterministic templates
produce a fully functional response. The system never degrades silently — it
always returns an answer, either from the model or from the template.

EXCLUDED MODELS (hackathon rules):
  - llama-3-405b-instruct
  - mistral-medium-2502
  - mistral-small-3-1-24b-instruct-2503

Token budget: enforced via WATSONX_MAX_TOKENS. Token usage is logged per call.
PII: never send cargo owner names, consignee details, or personal information.
     Pass IDs only; resolve locally.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ── Template library ───────────────────────────────────────────────────────────

_TEMPLATES = {
    "excursion_disposition": (
        "GDP Annex 5.5 classification: {severity} excursion on {shipment_id}. "
        "{degree_minutes:.0f} degree-minutes over {minutes_out_of_range} minutes. "
        "MKT: {mkt:.2f}°C. Peak: {peak_temp_c:.1f}°C. "
        "Disposition: {disposition}. "
        "Action required: {action}."
    ),
    "impact_summary": (
        "Disruption {disruption_id} ({disruption_type}, {severity}) is affecting "
        "{shipment_count} shipments. Estimated delay: {delay_hours:.0f}h. "
        "Confidence: {confidence:.0%}."
    ),
    "reroute_rationale": (
        "Recommended route: {summary}. "
        "Delta: {delta_days:+.1f} days, ${delta_cost_usd:,.0f} cost. "
        "Cold chain: {cold_chain_continuity}. "
        "Feasibility: {feasibility}."
    ),
    "idle_asset_summary": (
        "{asset_count} idle assets with {total_capacity_hours:.0f} total wasted capacity-hours. "
        "Top candidate: {top_asset_id} ({top_asset_type}) at {top_asset_location}, "
        "idle {top_idle_hours:.0f}h."
    ),
    "free_text_fallback": (
        "Based on current engine data: {engine_summary}. "
        "No language model available — this response was generated from deterministic engine output."
    ),
}


def _render_template(template_key: str, **kwargs) -> str:
    tpl = _TEMPLATES.get(template_key, _TEMPLATES["free_text_fallback"])
    try:
        return tpl.format(**kwargs)
    except KeyError as e:
        return f"[Template {template_key} missing key {e}] — engine data: {kwargs}"


# ── watsonx.ai client ─────────────────────────────────────────────────────────

class LLMClient:
    """
    Thin wrapper around watsonx.ai Granite instruct.
    Falls back to deterministic templates when:
      - WATSONX_ENABLED=false
      - API key absent or empty
      - Network error or timeout
      - Model returns empty response
    """

    def __init__(self):
        self.enabled = settings.watsonx_enabled and bool(settings.watsonx_api_key)
        self._client = None
        if self.enabled:
            self._init_client()

    def _init_client(self):
        try:
            from ibm_watsonx_ai import APIClient, Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference

            credentials = Credentials(
                url=settings.watsonx_url,
                api_key=settings.watsonx_api_key,
            )
            self._client = ModelInference(
                model_id=settings.watsonx_model_id,
                credentials=credentials,
                project_id=settings.watsonx_project_id,
                params={
                    "max_new_tokens": settings.watsonx_max_tokens,
                    "decoding_method": "greedy",
                    "temperature": 0.0,  # deterministic
                },
            )
            logger.info("watsonx.ai client initialised: model=%s", settings.watsonx_model_id)
        except ImportError:
            logger.warning("ibm-watsonx-ai not installed; falling back to templates")
            self.enabled = False
        except Exception as e:
            logger.warning("watsonx.ai init failed (%s); falling back to templates", e)
            self.enabled = False

    def generate(
        self,
        prompt: str,
        template_key: str = "free_text_fallback",
        template_kwargs: dict | None = None,
    ) -> dict[str, Any]:
        """
        Generate text. Returns:
            {
                "text": str,
                "source": "watsonx" | "template",
                "tokens_used": int | None,
                "model_id": str | None,
            }
        """
        if self.enabled and self._client is not None:
            try:
                import time
                t0 = time.monotonic()
                result = self._client.generate_text(prompt=prompt)
                elapsed = time.monotonic() - t0

                text = result if isinstance(result, str) else str(result)
                # Approximate token usage (watsonx client may expose this differently)
                tokens = len(prompt.split()) + len(text.split())
                logger.info(
                    "watsonx.ai generate: model=%s tokens≈%d elapsed=%.2fs",
                    settings.watsonx_model_id, tokens, elapsed,
                )

                if text.strip():
                    return {
                        "text": text.strip(),
                        "source": "watsonx",
                        "tokens_used": tokens,
                        "model_id": settings.watsonx_model_id,
                    }
            except Exception as e:
                logger.warning("watsonx.ai generate failed (%s); using template fallback", e)

        # Template fallback
        text = _render_template(template_key, **(template_kwargs or {}))
        return {
            "text": text,
            "source": "template",
            "tokens_used": None,
            "model_id": None,
        }


# Singleton client
_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
