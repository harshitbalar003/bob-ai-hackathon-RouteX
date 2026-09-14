"""
app/config.py — Application configuration via pydantic-settings.
All settings have defaults so the app runs with zero .env file.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./supply_chain.db"

    # ── Engine behaviour ──────────────────────────────────────────────────────
    # Gap threshold: if interval > nominal_interval_minutes * gap_multiplier
    # the gap is recorded rather than bridged.
    nominal_sensor_interval_minutes: int = 5
    gap_multiplier: int = 3

    # Excursion debounce: readings must return in-range for this many minutes
    # before the excursion is considered closed.
    excursion_debounce_minutes: int = 10

    # Stuck-value detection: flag sensor if identical value persists >= this
    stuck_value_minutes: int = 60

    # ── Priority queue weights ─────────────────────────────────────────────────
    pq_weight_severity: float = 0.45
    pq_weight_actionability: float = 0.25
    pq_weight_value: float = 0.20
    pq_weight_eta_slip: float = 0.30
    pq_weight_waste: float = 0.55
    pq_weight_match: float = 0.45

    # ── Features ──────────────────────────────────────────────────────────────
    feature_sse: bool = False          # SSE stream; set FEATURE_SSE=true to enable
    watsonx_enabled: bool = False      # language layer; no key needed for fallback

    # ── watsonx.ai (optional) ─────────────────────────────────────────────────
    watsonx_api_key: str = ""
    watsonx_project_id: str = ""
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    watsonx_model_id: str = "ibm/granite-13b-instruct-v2"
    watsonx_max_tokens: int = 512
    watsonx_timeout_seconds: int = 30

    # ── Engine versioning ─────────────────────────────────────────────────────
    engine_version: str = "1.0.0"


settings = Settings()
