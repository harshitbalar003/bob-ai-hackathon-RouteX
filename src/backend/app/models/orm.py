"""
app/models/orm.py — SQLAlchemy ORM table definitions.

Design: store JSON columns for complex nested fields (legs, cargo, etc.)
rather than full normalisation — this keeps the schema change cost low for a
hackathon while preserving the ability to filter on indexed top-level columns.

network_nodes and lanes are fully normalised — they are queried by the
rerouting engine on every path-search and benefit from indexed FK columns.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    __table_args__ = (
        # Composite index on (shipment_id, timestamp) — the hot path for
        # excursion detection and the /shipments/{id}/readings endpoint.
        # With 500k readings a table scan here kills demo responsiveness.
        Index("ix_sensor_readings_shipment_ts", "shipment_id", "timestamp"),
        # Unique constraint: makes ingestion idempotent
        UniqueConstraint("sensor_id", "timestamp", name="uq_sensor_reading"),
    )

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


class NetworkNodeRow(Base):
    """
    A port, airport, inland hub, or border crossing.
    Codes are UN/LOCODE (5-char) or IATA (3-char) for airports.
    All reference data — see docs/data-sources.md for provenance.
    """
    __tablename__ = "network_nodes"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # type: 'port' | 'airport' | 'hub' | 'border'
    node_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    lanes_from: Mapped[list["LaneRow"]] = relationship(
        "LaneRow", back_populates="from_node_obj", foreign_keys="LaneRow.from_node"
    )
    lanes_to: Mapped[list["LaneRow"]] = relationship(
        "LaneRow", back_populates="to_node_obj", foreign_keys="LaneRow.to_node"
    )


class LaneRow(Base):
    """
    A direct lane between two network nodes on a given mode/carrier.

    Indexed on (from_node, mode) — this is the hot path in the rerouting
    engine when building the outbound adjacency set for a node.

    cost_per_unit is synthetic (USD per kg); transit_hours is derived from
    published route data and carrier schedules.  See docs/data-sources.md.
    """
    __tablename__ = "lanes"
    __table_args__ = (
        Index("ix_lanes_from_node_mode", "from_node", "mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_node: Mapped[str] = mapped_column(
        String(10), ForeignKey("network_nodes.code"), nullable=False
    )
    to_node: Mapped[str] = mapped_column(
        String(10), ForeignKey("network_nodes.code"), nullable=False
    )
    # mode: 'ocean' | 'air' | 'road' | 'rail'
    mode: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    carrier: Mapped[str] = mapped_column(String, nullable=False)
    transit_hours: Mapped[float] = mapped_column(Float, nullable=False)
    cost_per_unit: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[float] = mapped_column(Float, nullable=False)
    reefer_capable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    from_node_obj: Mapped["NetworkNodeRow"] = relationship(
        "NetworkNodeRow", back_populates="lanes_from", foreign_keys=[from_node]
    )
    to_node_obj: Mapped["NetworkNodeRow"] = relationship(
        "NetworkNodeRow", back_populates="lanes_to", foreign_keys=[to_node]
    )


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
