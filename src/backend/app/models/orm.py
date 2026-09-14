"""
app/models/orm.py — SQLAlchemy ORM table definitions.

Design: store JSON columns for complex nested fields (legs, cargo, etc.)
rather than full normalisation — this keeps the schema change cost low for a
hackathon while preserving the ability to filter on indexed top-level columns.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ShipmentRow(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    reference: Mapped[str] = mapped_column(String, index=True)
    shipper: Mapped[str] = mapped_column(String)
    consignee: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    eta_original: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    eta_projected: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_cold_chain: Mapped[bool] = mapped_column(Boolean, index=True)
    regulatory_regime: Mapped[str | None] = mapped_column(String, nullable=True)
    cargo_value_usd: Mapped[float] = mapped_column(Float)
    impacted_by: Mapped[list] = mapped_column(JSON, default=list)
    # Full document stored as JSON for reads
    data: Mapped[dict] = mapped_column(JSON)


class DisruptionRow(Base):
    __tablename__ = "disruptions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_resolution_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, index=True, default=True)
    data: Mapped[dict] = mapped_column(JSON)


class SensorReadingRow(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # canonical reading_id
    shipment_id: Mapped[str] = mapped_column(String, index=True)
    sensor_id: Mapped[str] = mapped_column(String, index=True)
    leg_id: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    temp_c: Mapped[float] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    door_open: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class SensorGapRow(Base):
    __tablename__ = "sensor_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(String, index=True)
    sensor_id: Mapped[str] = mapped_column(String)
    leg_id: Mapped[str] = mapped_column(String, index=True)
    gap_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gap_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer)


class ExcursionRow(Base):
    __tablename__ = "excursions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    shipment_id: Mapped[str] = mapped_column(String, index=True)
    leg_id: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    severity: Mapped[str] = mapped_column(String, index=True)
    disposition: Mapped[str] = mapped_column(String)
    detected_before_delivery: Mapped[bool] = mapped_column(Boolean, index=True)
    degree_minutes: Mapped[float] = mapped_column(Float)
    minutes_out_of_range: Mapped[int] = mapped_column(Integer)
    peak_temp_c: Mapped[float] = mapped_column(Float)
    mean_kinetic_temp_c: Mapped[float] = mapped_column(Float)
    rule_pack_id: Mapped[str] = mapped_column(String)
    rule_id: Mapped[str] = mapped_column(String)
    citation: Mapped[str] = mapped_column(String)
    evidence_reading_ids: Mapped[list] = mapped_column(JSON, default=list)
    data: Mapped[dict] = mapped_column(JSON)


class FleetAssetRow(Base):
    __tablename__ = "fleet_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    reefer_capable: Mapped[bool] = mapped_column(Boolean, index=True)
    idle_since_hours: Mapped[float] = mapped_column(Float)
    capacity_value: Mapped[float] = mapped_column(Float)
    capacity_unit: Mapped[str] = mapped_column(String)
    home_depot: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)


class RedeploymentMatchRow(Base):
    __tablename__ = "redeployment_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String, index=True)
    shipment_id: Mapped[str] = mapped_column(String, index=True)
    distance_km: Mapped[float] = mapped_column(Float)
    hours_to_position: Mapped[float] = mapped_column(Float)
    utilisation_gain_pct: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RerouteOptionRow(Base):
    __tablename__ = "reroute_options"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    shipment_id: Mapped[str] = mapped_column(String, index=True)
    feasibility: Mapped[str] = mapped_column(String)
    cold_chain_continuity: Mapped[str] = mapped_column(String)
    recommended: Mapped[bool] = mapped_column(Boolean)
    delta_days: Mapped[float] = mapped_column(Float)
    delta_cost_usd: Mapped[float] = mapped_column(Float)
    data: Mapped[dict] = mapped_column(JSON)
