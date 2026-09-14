"""
app/seed/telemetry.py — Physical telemetry generator for cold-chain shipments.

Model: first-order thermal system discretised at 5-minute intervals.

    T[t+1] = T[t]
             + (Δt/τ_thermal) × (T_ambient - T[t])       # thermal leak
             − (Δt/τ_cooling) × (T[t] - T_setpoint) × cooling_on
             + door_gain_per_min × door_open_minutes      # door event
             + N(0, σ_noise)                              # instrument noise

All parameters are sourced from published literature — see docs/data-sources.md.

Physical constants:
    τ_thermal = 240 min (4 h)  — thermal time constant of a reefer container
    τ_cooling  = 90 min       — refrigeration recovery time constant
    σ_noise    = 0.05 °C      — instrument noise (calibrated sensor)
    door_gain  = 0.08 °C/min  — heat ingress per minute of door open

Six scripted telemetry scenarios (deterministic, seed-independent):
    clean_run                  — fully in-range, no events
    clean_run_minor_excursion  — door-open event causes 40-min minor excursion
    critical_excursion_open    — power disconnect in yard; temp drifts past max
    freezing_excursion_resolved — ambient cold shock; temp drops below min
    sensor_gap_and_stuck       — 215-min gap + 90-min stuck value
    (ambient_clean_run)        — wide range (USP_1079), always in range
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.orm import SensorGapRow, SensorReadingRow

# ── Physical constants ────────────────────────────────────────────────────────
_DELTA_T_MIN = 5             # reading interval (minutes)
_DELTA_T_H = _DELTA_T_MIN / 60.0

_TAU_THERMAL_MIN = 240.0     # thermal time constant (min) — reefer container
_TAU_COOLING_MIN = 90.0      # cooling recovery time constant (min)
_SIGMA_NOISE = 0.05          # instrument noise σ (°C)
_DOOR_GAIN_PER_MIN = 0.08    # temperature rise per door-open minute (°C/min)
_HUMIDITY_NOMINAL = 85.0     # nominal humidity inside reefer (%)
_HUMIDITY_NOISE = 1.5        # humidity noise σ


@dataclass
class TelemetryEvent:
    """A discrete event applied to the simulation during a time window."""
    start_min: int        # minutes from leg start
    end_min: int          # minutes from leg start
    event_type: str       # 'door_open' | 'power_off' | 'ambient_cold' | 'gap' | 'stuck'
    magnitude: float = 0.0   # °C step for ambient_cold


@dataclass
class TelemetryScript:
    """A complete telemetry specification for one leg."""
    leg_duration_min: int
    t_setpoint: float             # target temperature (°C)
    t_ambient_base: float         # base ambient temperature (°C)
    t_start: float                # initial cargo temperature (°C)
    events: list[TelemetryEvent] = field(default_factory=list)
    gap_start_min: Optional[int] = None    # if set, a sensor gap starts here
    gap_end_min: Optional[int] = None
    stuck_start_min: Optional[int] = None  # if set, sensor reports constant value here
    stuck_end_min: Optional[int] = None


def _reading_id(shipment_id: str, sensor_id: str, ts: datetime) -> str:
    ts_ms = int(ts.timestamp() * 1000)
    return f"{shipment_id}:{sensor_id}:{ts_ms}"


def simulate_leg(
    script: TelemetryScript,
    shipment_id: str,
    leg_id: str,
    sensor_id: str,
    leg_start_utc: datetime,
    rng,
    temp_range_min: float,
    temp_range_max: float,
) -> tuple[list[SensorReadingRow], list[SensorGapRow]]:
    """
    Run the thermal simulation for one leg and return ORM row lists.

    The simulation is deterministic given the script; rng is used only for
    noise (instrument measurement uncertainty). The scripted events (door
    opens, power-off, ambient cold) are not randomised.

    Args:
        script: TelemetryScript describing the physical events for this leg.
        shipment_id: Parent shipment ID.
        leg_id: This leg's ID.
        sensor_id: Sensor ID (e.g. 'sen-101-a').
        leg_start_utc: When the leg begins (UTC datetime).
        rng: numpy.random.Generator — for noise only.
        temp_range_min: Lower bound of allowed range (°C).
        temp_range_max: Upper bound of allowed range (°C).

    Returns:
        (readings, gaps) — ORM row lists for bulk insert.
    """
    n_steps = script.leg_duration_min // _DELTA_T_MIN
    readings: list[SensorReadingRow] = []
    gaps: list[SensorGapRow] = []

    t_cargo = script.t_start
    t_ambient = script.t_ambient_base
    cooling_on = True

    # Build an event map: minute → list of events active at that minute
    active_at: dict[int, list[TelemetryEvent]] = {}
    for ev in script.events:
        for m in range(ev.start_min, ev.end_min, _DELTA_T_MIN):
            active_at.setdefault(m, []).append(ev)

    # Gap and stuck-value tracking
    in_gap = False
    in_stuck = False
    stuck_value: float = 0.0
    gap_start_ts: datetime | None = None

    for step in range(n_steps):
        t_min = step * _DELTA_T_MIN
        ts = leg_start_utc + timedelta(minutes=t_min)

        # ── Gap handling ──────────────────────────────────────────────
        if script.gap_start_min is not None and t_min == script.gap_start_min:
            in_gap = True
            # gap_start_ts = last reading BEFORE the gap (previous step)
            gap_start_ts = leg_start_utc + timedelta(minutes=t_min - _DELTA_T_MIN)
        if script.gap_end_min is not None and t_min == script.gap_end_min:
            in_gap = False
            if gap_start_ts is not None:
                gap_end_ts = ts
                duration_min = int((gap_end_ts - gap_start_ts).total_seconds() / 60)
                gaps.append(SensorGapRow(
                    shipment_id=shipment_id,
                    sensor_id=sensor_id,
                    leg_id=leg_id,
                    gap_start_at=gap_start_ts,
                    gap_end_at=gap_end_ts,
                    duration_minutes=duration_min,
                ))
                gap_start_ts = None

        if in_gap:
            # No reading emitted during gap — this is the compliance finding
            continue

        # ── Stuck-value handling ──────────────────────────────────────
        if script.stuck_start_min is not None and t_min == script.stuck_start_min:
            in_stuck = True
            stuck_value = t_cargo
        if script.stuck_end_min is not None and t_min == script.stuck_end_min:
            in_stuck = False

        # ── Physics update ────────────────────────────────────────────
        events_now = active_at.get(t_min, [])
        door_open = False
        door_open_minutes = 0.0

        for ev in events_now:
            if ev.event_type == "door_open":
                door_open = True
                door_open_minutes = min(_DELTA_T_MIN, ev.end_min - t_min)
            elif ev.event_type == "power_off":
                cooling_on = False
            elif ev.event_type == "ambient_cold":
                t_ambient = script.t_ambient_base + ev.magnitude

        # After power-off events end, refrigeration restores gradually
        if not events_now and not cooling_on:
            # Check if any power_off event is still active past this minute
            any_poweroff = any(
                ev.event_type == "power_off" and ev.end_min > t_min
                for ev in script.events
            )
            if not any_poweroff:
                cooling_on = True
                t_ambient = script.t_ambient_base  # restore ambient

        # Thermal leak: cargo drifts toward ambient
        dt_thermal = (_DELTA_T_MIN / _TAU_THERMAL_MIN) * (t_ambient - t_cargo)

        # Cooling pull-back (only when powered on)
        dt_cooling = 0.0
        if cooling_on:
            dt_cooling = (_DELTA_T_MIN / _TAU_COOLING_MIN) * (t_cargo - script.t_setpoint)

        # Door-open heat ingress
        dt_door = _DOOR_GAIN_PER_MIN * door_open_minutes

        # Instrument noise
        noise = float(rng.normal(0, _SIGMA_NOISE))

        t_cargo = t_cargo + dt_thermal - dt_cooling + dt_door + noise
        # Physical clamp: cargo cannot be colder than ambient (basic sanity)
        # Removed clamp to allow freezing excursions below ambient
        t_cargo = max(t_cargo, -25.0)  # absolute minimum (sensor range)
        t_cargo = min(t_cargo, 40.0)   # absolute maximum

        # Report temperature
        reported_temp = stuck_value if in_stuck else t_cargo
        humidity = _HUMIDITY_NOMINAL + float(rng.normal(0, _HUMIDITY_NOISE))
        humidity = max(50.0, min(99.9, humidity))

        rid = _reading_id(shipment_id, sensor_id, ts)
        readings.append(SensorReadingRow(
            id=rid,
            shipment_id=shipment_id,
            sensor_id=sensor_id,
            leg_id=leg_id,
            timestamp=ts,
            temp_c=round(reported_temp, 2),
            humidity_pct=round(humidity, 1),
            door_open=door_open,
        ))

    # Close any open gap at end of leg
    if in_gap and gap_start_ts is not None:
        gap_end_ts = leg_start_utc + timedelta(minutes=script.leg_duration_min)
        duration_min = int((gap_end_ts - gap_start_ts).total_seconds() / 60)
        gaps.append(SensorGapRow(
            shipment_id=shipment_id,
            sensor_id=sensor_id,
            leg_id=leg_id,
            gap_start_at=gap_start_ts,
            gap_end_at=gap_end_ts,
            duration_minutes=duration_min,
        ))

    return readings, gaps


# ── Scripted scenarios ────────────────────────────────────────────────────────

def _build_script_clean_run(
    leg_duration_min: int,
    t_setpoint: float,
    t_ambient: float,
) -> TelemetryScript:
    """Refrigeration holds throughout; no events. Always in-range."""
    return TelemetryScript(
        leg_duration_min=leg_duration_min,
        t_setpoint=t_setpoint,
        t_ambient_base=t_ambient,
        t_start=t_setpoint + 0.5,  # slight above setpoint at start
        events=[],
    )


def _build_script_clean_run_minor_excursion(
    leg_duration_min: int,
    t_setpoint: float,
    t_ambient: float,
    temp_range_max: float,
) -> TelemetryScript:
    """
    Single door-open event at t=3h causes a ~40-min rise to ~1°C above max.
    Door-correlated. Classifies as minor (short, low degree-minutes).
    """
    door_start = 180   # 3h into leg (minutes)
    door_end = door_start + 45   # 45-min door event (loading/unloading)
    return TelemetryScript(
        leg_duration_min=leg_duration_min,
        t_setpoint=t_setpoint,
        t_ambient_base=t_ambient,
        t_start=t_setpoint + 0.3,
        events=[
            TelemetryEvent(
                start_min=door_start,
                end_min=door_end,
                event_type="door_open",
            ),
        ],
    )


def _build_script_critical_excursion_open(
    leg_duration_min: int,
    t_setpoint: float,
    t_ambient: float,
    temp_range_max: float,
) -> TelemetryScript:
    """
    Yard dwell with power disconnect: refrigeration off from t=5h onwards.
    Cargo temperature drifts toward ambient (25°C) on thermal mass alone.
    Excursion crosses max within ~2h of disconnect and stays open.

    This is the DEMO scenario — the operator must see this, act, and the
    reroute with cold-chain continuity is the recommended action.
    """
    power_off_start = 300   # 5h into leg
    power_off_end = leg_duration_min  # never restored (still in transit)
    return TelemetryScript(
        leg_duration_min=leg_duration_min,
        t_setpoint=t_setpoint,
        t_ambient_base=25.0,   # yard ambient (summer)
        t_start=t_setpoint + 0.2,
        events=[
            TelemetryEvent(
                start_min=power_off_start,
                end_min=power_off_end,
                event_type="power_off",
            ),
        ],
    )


def _build_script_freezing_excursion_resolved(
    leg_duration_min: int,
    t_setpoint: float,
    t_ambient: float,
    temp_range_min: float,
) -> TelemetryScript:
    """
    Unheated warehouse ambient drops to -5°C for 2h, pushing cargo below min.
    Refrigeration stays on (warming mode not modelled) — cargo drifts cold.
    Excursion lasts ~110 min, then recovers when ambient restores.

    Classifies as minor-resolved (short duration, low degree-minutes for
    freeze; but severity asymmetry applies for vaccine cargo → may be major).
    """
    cold_start = int(leg_duration_min * 0.3)   # 30% into leg
    cold_end = cold_start + 120                # 2h cold ambient
    return TelemetryScript(
        leg_duration_min=leg_duration_min,
        t_setpoint=t_setpoint,
        t_ambient_base=t_ambient,
        t_start=t_setpoint + 0.5,
        events=[
            TelemetryEvent(
                start_min=cold_start,
                end_min=cold_end,
                event_type="ambient_cold",
                magnitude=-28.0,  # ambient drops to t_ambient - 28 ≈ -5°C
            ),
        ],
    )


def _build_script_sensor_gap_and_stuck(
    leg_duration_min: int,
    t_setpoint: float,
    t_ambient: float,
) -> TelemetryScript:
    """
    Normal telemetry until t=3h10m.
    Gap: 215 minutes (3h35m) starting at t=3h10m.
    After gap, sensor reports stuck value for 90 minutes.
    No temperature excursion — the gap itself is the compliance finding.
    """
    gap_start = 190    # gap starts at t=190; last reading before gap at t=185
    gap_end = 185 + 215   # = 400; first reading after gap; duration = 400-185 = 215 min
    stuck_start = gap_end
    stuck_end = stuck_start + 90
    return TelemetryScript(
        leg_duration_min=leg_duration_min,
        t_setpoint=t_setpoint,
        t_ambient_base=t_ambient,
        t_start=t_setpoint + 0.4,
        events=[],
        gap_start_min=gap_start,
        gap_end_min=gap_end,
        stuck_start_min=stuck_start,
        stuck_end_min=stuck_end,
    )


# ── Script dispatcher ─────────────────────────────────────────────────────────

_SCRIPT_BUILDERS = {
    "clean_run": _build_script_clean_run,
    "clean_run_minor_excursion": _build_script_clean_run_minor_excursion,
    "critical_excursion_open": _build_script_critical_excursion_open,
    "freezing_excursion_resolved": _build_script_freezing_excursion_resolved,
    "sensor_gap_and_stuck": _build_script_sensor_gap_and_stuck,
}

_AMBIENT_BY_LEG_MODE = {
    "ocean": 24.0,   # sea-level ambient
    "air": 22.0,     # controlled cargo hold (pressure-compensated)
    "road": 22.0,    # European summer road ambient
    "rail": 20.0,    # rail ambient
}


def build_script_for(
    script_name: str,
    leg_duration_min: int,
    temp_range_min: float,
    temp_range_max: float,
    mode: str = "ocean",
) -> TelemetryScript:
    """
    Instantiate the correct TelemetryScript for a named script.

    The setpoint is the midpoint of the allowed range.
    Ambient is chosen by mode and adjusted for the script.
    """
    t_setpoint = (temp_range_min + temp_range_max) / 2.0
    t_ambient = _AMBIENT_BY_LEG_MODE.get(mode, 22.0)

    builder = _SCRIPT_BUILDERS.get(script_name)
    if builder is None:
        # Unknown script → clean run
        return _build_script_clean_run(leg_duration_min, t_setpoint, t_ambient)

    # Each builder has a slightly different signature — handle via arg check
    import inspect
    sig = inspect.signature(builder)
    params = list(sig.parameters.keys())

    if script_name == "clean_run":
        return builder(leg_duration_min, t_setpoint, t_ambient)
    elif script_name == "clean_run_minor_excursion":
        return builder(leg_duration_min, t_setpoint, t_ambient, temp_range_max)
    elif script_name == "critical_excursion_open":
        return builder(leg_duration_min, t_setpoint, t_ambient, temp_range_max)
    elif script_name == "freezing_excursion_resolved":
        return builder(leg_duration_min, t_setpoint, t_ambient, temp_range_min)
    elif script_name == "sensor_gap_and_stuck":
        return builder(leg_duration_min, t_setpoint, t_ambient)
    else:
        return _build_script_clean_run(leg_duration_min, t_setpoint, t_ambient)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_telemetry_for_shipment(
    scripted_shipment_spec: dict,
    shipment_row,  # ShipmentRow
    rng,
) -> tuple[list[SensorReadingRow], list[SensorGapRow]]:
    """
    Generate all sensor readings and gaps for one scripted cold-chain shipment.

    Args:
        scripted_shipment_spec: The entry from scenario['scripted_shipments'].
        shipment_row: The ShipmentRow produced by generate_scripted_shipments.
        rng: numpy.random.Generator.

    Returns:
        (readings, gaps) for all legs of the shipment.
    """
    all_readings: list[SensorReadingRow] = []
    all_gaps: list[SensorGapRow] = []

    script_name = scripted_shipment_spec["telemetry_script"]
    temp_range = scripted_shipment_spec.get("temp_range_c", {"min": 2.0, "max": 8.0})
    temp_min = temp_range["min"]
    temp_max = temp_range["max"]

    legs = shipment_row.data.get("legs", [])
    sensor_suffix = 0

    for leg_data in legs:
        sensor_suffix += 1
        leg_id = leg_data["id"]
        sensor_id = f"sen-{shipment_row.id[4:]}-{chr(ord('a') + sensor_suffix - 1)}"

        # Parse leg timing
        departs_str = leg_data["departsAt"]
        arrives_str = leg_data["arrivesAt"]
        leg_start = datetime.fromisoformat(departs_str.replace("Z", "+00:00"))
        leg_end = datetime.fromisoformat(arrives_str.replace("Z", "+00:00"))
        leg_duration_min = max(60, int((leg_end - leg_start).total_seconds() / 60))
        # Cap at 24h for the gap/stuck scenario to keep data volume reasonable
        # (sensor readings are every 5 min; 24h = 288 readings per leg)
        leg_duration_min = min(leg_duration_min, 1440)

        mode = leg_data.get("mode", "ocean")

        # First leg gets the scripted behaviour; subsequent legs are clean runs
        # (except for sensor_gap_and_stuck which is scripted on leg 2)
        if sensor_suffix == 1:
            effective_script = script_name
        elif script_name == "sensor_gap_and_stuck" and sensor_suffix == 2:
            effective_script = script_name
        else:
            effective_script = "clean_run"

        script = build_script_for(
            effective_script,
            leg_duration_min,
            temp_min,
            temp_max,
            mode=mode,
        )

        leg_readings, leg_gaps = simulate_leg(
            script=script,
            shipment_id=shipment_row.id,
            leg_id=leg_id,
            sensor_id=sensor_id,
            leg_start_utc=leg_start,
            rng=rng,
            temp_range_min=temp_min,
            temp_range_max=temp_max,
        )
        all_readings.extend(leg_readings)
        all_gaps.extend(leg_gaps)

    return all_readings, all_gaps
