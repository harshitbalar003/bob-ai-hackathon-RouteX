"""
app/engines/cold_chain.py — Cold chain excursion detection and severity classification.

This is the deterministic core. No network calls, no model calls. Given a series of
SensorReadings and the active RulePack for a shipment leg, this engine:

  1. Cleans the series (sort, dedup, gap detection, stuck-value flagging)
  2. Detects excursions (contiguous out-of-range runs with debounce)
  3. Computes degree-minutes and MKT per excursion and per leg
  4. Classifies each excursion against the rule pack (first-match)
  5. Returns ExcursionWithDecision records with full audit trail

Mean Kinetic Temperature (MKT) formula:
    T_mkt = (ΔH/R) / −ln( Σ(e^(−ΔH/(R·T_i))) / n )

    ΔH = 83,144 J/mol (activation energy for typical pharmaceutical degradation)
    R  = 8.314 J/(mol·K)
    T_i in Kelvin; result converted to °C

Sources:
    - Grimm, W. "Stability testing in the EC" (1993) — original MKT pharmacopoeial use
    - USP General Chapter <1079> "Good Storage and Distribution Practices for Drug
      Products", Table 1 worked example (MKT calculation at 25°C nominal)
    - WHO Technical Report Series No. 961 (2011), Annex 9 §5 (MKT for vaccine chains)
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Sequence

from app.config import settings
from app.models.domain import (
    DataGap,
    Decision,
    ExcursionDisposition,
    ExcursionWithDecision,
    RulePack,
    Severity,
    SeverityRule,
)
from app.models.domain import Excursion as ExcursionModel
from app.models.domain import SensorReading

# ── MKT constants ────────────────────────────────────────────────────────────
# Activation energy for pharmaceutical degradation (J/mol)
_DELTA_H_J_PER_MOL: float = 83_144.0
# Universal gas constant (J/(mol·K))
_R_J_PER_MOL_K: float = 8.314
# Ratio used in every MKT calculation
_DH_OVER_R: float = _DELTA_H_J_PER_MOL / _R_J_PER_MOL_K   # ≈ 10_000.7


def compute_mean_kinetic_temp_c(temps_c: Sequence[float]) -> float:
    """
    Compute Mean Kinetic Temperature (MKT) over a sequence of temperature readings.

    Formula (USP <1079>):
        T_mkt = (ΔH/R) / −ln( (Σ e^(−ΔH/(R·T_i))) / n )

    where T_i is in Kelvin and the result is converted back to °C.

    Args:
        temps_c: Sequence of temperature readings in °C. Must be non-empty.

    Returns:
        MKT in °C.

    Raises:
        ValueError: if temps_c is empty.

    Reference:
        USP General Chapter <1079>, Table 1 worked example.
        WHO TRS 961 Annex 9 §5.
    """
    if not temps_c:
        raise ValueError("temps_c must be non-empty")

    temps_k = [t + 273.15 for t in temps_c]
    n = len(temps_k)

    # Σ e^(−ΔH/(R·T_i))
    arrhenius_sum = sum(math.exp(-_DH_OVER_R / t_k) for t_k in temps_k)
    avg = arrhenius_sum / n

    # Guard: avg should be > 0 by construction; log(avg) will be negative
    # because exp(-10000/T) << 1 for physiological temperatures
    t_mkt_k = _DH_OVER_R / (-math.log(avg))
    return t_mkt_k - 273.15


def compute_degree_minutes(
    readings: list[SensorReading],
    range_min: float,
    range_max: float,
) -> float:
    """
    Compute degree-minutes for a sequence of readings against a temperature range.

    Σ |T_i − T_limit| × Δt_i (minutes) for each reading outside the range,
    where T_limit is the nearer boundary that was crossed.

    Args:
        readings: Must be sorted by timestamp and all outside the allowed range.
        range_min: Lower bound of allowed range (°C).
        range_max: Upper bound of allowed range (°C).

    Returns:
        Degree-minutes as a float.
    """
    if len(readings) < 2:
        if len(readings) == 1:
            # Single-reading excursion: 0 elapsed time, 0 degree-minutes
            return 0.0
        return 0.0

    dm = 0.0
    for i in range(len(readings) - 1):
        r = readings[i]
        r_next = readings[i + 1]
        dt_min = (r_next.timestamp - r.timestamp).total_seconds() / 60.0
        if dt_min <= 0:
            continue
        t = r.temp_c
        if t > range_max:
            dm += (t - range_max) * dt_min
        elif t < range_min:
            dm += (range_min - t) * dt_min
    # Include the last point's contribution with a 5-minute forward window
    # (assume reading interval for the tail)
    last = readings[-1]
    t = last.temp_c
    if t > range_max:
        dm += (t - range_max) * settings.nominal_sensor_interval_minutes
    elif t < range_min:
        dm += (range_min - t) * settings.nominal_sensor_interval_minutes

    return dm


# ── Data cleaning ─────────────────────────────────────────────────────────────

class CleanedSeries:
    """Result of cleaning a raw sensor reading series."""

    def __init__(
        self,
        readings: list[SensorReading],
        gaps: list[DataGap],
        sensor_suspect: bool,
        suspect_reason: str,
    ):
        self.readings = readings
        self.gaps = gaps
        self.sensor_suspect = sensor_suspect
        self.suspect_reason = suspect_reason


def clean_series(
    raw: list[SensorReading],
    *,
    shipment_id: str,
    leg_id: str,
    is_cold_chain: bool,
    gap_threshold_minutes: int | None = None,
    stuck_value_minutes: int | None = None,
) -> CleanedSeries:
    """
    Sort, dedup, detect gaps, and flag stuck sensors.

    Gap detection: if interval between consecutive readings exceeds
    nominal_interval × gap_multiplier, record a DataGap. A gap over a
    cold-chain leg is itself a compliance finding.

    Stuck-value detection: flag sensor if the identical temperature value
    is reported for ≥ stuck_value_minutes. Lowers confidence on classifications.

    Out-of-order and duplicate readings: sorted by timestamp; deduplicated
    by (sensor_id, timestamp), keeping the first occurrence.
    """
    if gap_threshold_minutes is None:
        gap_threshold_minutes = (
            settings.nominal_sensor_interval_minutes * settings.gap_multiplier
        )
    if stuck_value_minutes is None:
        stuck_value_minutes = settings.stuck_value_minutes

    # Sort by timestamp
    sorted_readings = sorted(raw, key=lambda r: r.timestamp)

    # Dedup by (sensor_id, timestamp) — keep first
    seen: set[tuple[str, datetime]] = set()
    deduped: list[SensorReading] = []
    for r in sorted_readings:
        key = (r.sensor_id, r.timestamp)
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # Gap detection
    gaps: list[DataGap] = []
    cleaned: list[SensorReading] = []
    if deduped:
        cleaned.append(deduped[0])
        for i in range(1, len(deduped)):
            prev = deduped[i - 1]
            curr = deduped[i]
            dt_min = (curr.timestamp - prev.timestamp).total_seconds() / 60.0
            if dt_min > gap_threshold_minutes:
                gaps.append(
                    DataGap(
                        shipment_id=shipment_id,
                        sensor_id=curr.sensor_id,
                        leg_id=leg_id,
                        gap_start_at=prev.timestamp,
                        gap_end_at=curr.timestamp,
                        duration_minutes=dt_min,
                        is_compliance_finding=is_cold_chain,
                    )
                )
                # Do NOT append prev again; gap readings are excluded from analysis
            cleaned.append(curr)

    # Stuck-value detection
    sensor_suspect = False
    suspect_reason = ""
    if cleaned:
        max_run_min = _longest_stuck_run_minutes(cleaned)
        if max_run_min >= stuck_value_minutes:
            sensor_suspect = True
            suspect_reason = (
                f"Sensor reported identical temperature for {max_run_min:.0f} min "
                f"(threshold: {stuck_value_minutes} min)"
            )

    return CleanedSeries(
        readings=cleaned,
        gaps=gaps,
        sensor_suspect=sensor_suspect,
        suspect_reason=suspect_reason,
    )


def _longest_stuck_run_minutes(readings: list[SensorReading]) -> float:
    """Return the longest run of consecutive identical tempC values in minutes."""
    if len(readings) < 2:
        return 0.0
    max_run = 0.0
    run_start = readings[0].timestamp
    run_val = readings[0].temp_c
    for i in range(1, len(readings)):
        if readings[i].temp_c == run_val:
            # extend run
            pass
        else:
            # end of run
            run_min = (readings[i - 1].timestamp - run_start).total_seconds() / 60.0
            max_run = max(max_run, run_min)
            run_start = readings[i].timestamp
            run_val = readings[i].temp_c
    # close final run
    final_run = (readings[-1].timestamp - run_start).total_seconds() / 60.0
    max_run = max(max_run, final_run)
    return max_run


# ── Excursion detection ───────────────────────────────────────────────────────

class _ExcursionCandidate:
    """Mutable state during excursion building."""

    def __init__(self, first: SensorReading, range_min: float, range_max: float):
        self.readings: list[SensorReading] = [first]
        self.range_min = range_min
        self.range_max = range_max
        # Debounce: track in-range readings that might close the excursion
        self._pending_close: list[SensorReading] = []

    @property
    def started_at(self) -> datetime:
        return self.readings[0].timestamp

    @property
    def peak_temp_c(self) -> float:
        return max(
            (abs(r.temp_c - self.range_max) if r.temp_c > self.range_max
             else abs(self.range_min - r.temp_c))
            for r in self.readings
            if r.temp_c > self.range_max or r.temp_c < self.range_min
        ) + (
            self.range_max
            if any(r.temp_c > self.range_max for r in self.readings)
            else -999
        )

    @property
    def actual_peak_temp_c(self) -> float:
        """The actual temperature value at peak (not delta from boundary)."""
        temps = [r.temp_c for r in self.readings
                 if r.temp_c > self.range_max or r.temp_c < self.range_min]
        if not temps:
            return 0.0
        # If warming excursion, peak is max; if freezing, peak is min (most extreme)
        above = [t for t in temps if t > self.range_max]
        below = [t for t in temps if t < self.range_min]
        if above and below:
            # Mixed — return whichever has more extreme deviation
            max_above_delta = max(above) - self.range_max
            max_below_delta = self.range_min - min(below)
            return max(above) if max_above_delta >= max_below_delta else min(below)
        if above:
            return max(above)
        return min(below)

    @property
    def is_freezing(self) -> bool:
        return any(r.temp_c < self.range_min for r in self.readings)

    def out_of_range_readings(self) -> list[SensorReading]:
        return [r for r in self.readings
                if r.temp_c > self.range_max or r.temp_c < self.range_min]

    def add_in_range(self, r: SensorReading) -> None:
        self._pending_close.append(r)

    def commit_close(self) -> None:
        """Debounce period passed — the in-range readings were genuine recovery."""
        self.readings.extend(self._pending_close)
        self._pending_close.clear()

    def reopen(self, r: SensorReading) -> None:
        """New out-of-range reading arrived during debounce — excursion continues."""
        self.readings.extend(self._pending_close)
        self._pending_close.clear()
        self.readings.append(r)

    def is_debouncing(self) -> bool:
        return bool(self._pending_close)

    @property
    def debounce_started_at(self) -> datetime | None:
        if self._pending_close:
            return self._pending_close[0].timestamp
        return None


def detect_excursions(
    readings: list[SensorReading],
    rule_pack: RulePack,
    debounce_minutes: int | None = None,
) -> list[list[SensorReading]]:
    """
    Detect contiguous out-of-range runs from a cleaned, sorted reading series.

    An excursion ends when readings return in-range AND stay in-range for the
    debounce window — this prevents a single noisy sensor from producing forty
    excursions.

    Returns a list of reading groups, one per excursion. Each group contains
    only the out-of-range readings (and the bordering in-range readings that
    bookend it).

    Args:
        readings: Cleaned, sorted SensorReading list.
        rule_pack: Active RulePack (provides allowed_range_c).
        debounce_minutes: Override for debounce window. Defaults to config value.

    Returns:
        List of lists; each inner list is one excursion's readings.
    """
    if debounce_minutes is None:
        debounce_minutes = settings.excursion_debounce_minutes

    range_min = rule_pack.allowed_range_c.min
    range_max = rule_pack.allowed_range_c.max

    excursions: list[list[SensorReading]] = []
    current: _ExcursionCandidate | None = None

    for r in readings:
        out = r.temp_c > range_max or r.temp_c < range_min

        if current is None:
            if out:
                current = _ExcursionCandidate(r, range_min, range_max)
        else:
            if out:
                if current.is_debouncing():
                    current.reopen(r)
                else:
                    current.readings.append(r)
            else:
                # In range
                if current.is_debouncing():
                    # Check if debounce window has elapsed
                    elapsed = (r.timestamp - current.debounce_started_at).total_seconds() / 60.0
                    if elapsed >= debounce_minutes:
                        # Genuine recovery — close the excursion
                        current.commit_close()
                        oor = current.out_of_range_readings()
                        if oor:
                            excursions.append(current.readings)
                        current = None
                    else:
                        current.add_in_range(r)
                else:
                    current.add_in_range(r)

    # Handle still-open excursion at end of series
    if current is not None:
        oor = current.out_of_range_readings()
        if oor:
            all_readings = current.readings + current._pending_close
            excursions.append(all_readings)

    return excursions


# ── Rule matching ─────────────────────────────────────────────────────────────

def _cargo_tags_from_description(description: str) -> list[str]:
    """Derive cargo category tags from a cargo description string (lowercase)."""
    desc_lower = description.lower()
    tags: list[str] = []
    tag_keywords = {
        "vaccines": ["vaccine", "vaccination"],
        "biologics": ["biologic", "biological", "mab", "monoclonal"],
        "insulin": ["insulin"],
        "blood_products": ["blood", "plasma", "serum"],
        "freeze_sensitive": ["freeze-sensitive", "freeze sensitive"],
        "dtp": ["dtp", "diphtheria", "tetanus", "pertussis"],
        "hep_b": ["hepatitis b", "hep b", "hepb"],
        "hib": ["haemophilus", "hib"],
        "fresh_produce": ["produce", "vegetable", "fruit", "fresh"],
        "beverages": ["beverage", "drink", "juice"],
        "dairy": ["dairy", "milk", "cheese", "yogurt"],
    }
    for tag, keywords in tag_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            tags.append(tag)
    return tags


def match_rule(
    rule_pack: RulePack,
    degree_minutes: float,
    minutes_out_of_range: float,
    peak_temp_c: float,
    is_freezing: bool,
    cargo_description: str = "",
) -> SeverityRule | None:
    """
    Evaluate severity rules in order; return the first that matches.

    All non-None conditions within a rule must hold (logical AND).
    """
    cargo_tags = _cargo_tags_from_description(cargo_description)
    range_min = rule_pack.allowed_range_c.min
    range_max = rule_pack.allowed_range_c.max

    for rule in rule_pack.severity_rules:
        # Filter by cargo type if specified
        if rule.applies_to_cargo is not None:
            if not any(tag in rule.applies_to_cargo for tag in cargo_tags):
                continue

        # below_range filter
        if rule.below_range is not None:
            if rule.below_range and not is_freezing:
                continue
            if not rule.below_range and is_freezing:
                continue

        # degree-minutes floor
        if rule.min_degree_minutes is not None:
            if degree_minutes < rule.min_degree_minutes:
                continue

        # minutes out of range floor
        if rule.min_minutes_out_of_range is not None:
            if minutes_out_of_range < rule.min_minutes_out_of_range:
                continue

        # max_temp_exceeded_by: how many °C above max (or below min for freeze)
        if rule.max_temp_exceeded_by_c is not None:
            if is_freezing:
                # How much below range_min
                delta = range_min - peak_temp_c
            else:
                delta = peak_temp_c - range_max
            if delta < rule.max_temp_exceeded_by_c:
                continue

        # All conditions matched
        return rule

    return None


# ── Main entry point ──────────────────────────────────────────────────────────

def analyse_leg(
    readings: list[SensorReading],
    rule_pack: RulePack,
    shipment_id: str,
    leg_id: str,
    cargo_description: str,
    is_leg_complete: bool,
    delivery_eta: datetime | None,
    engine_version: str | None = None,
) -> tuple[list[ExcursionWithDecision], list[DataGap], bool]:
    """
    Full cold-chain analysis for one leg.

    Steps:
      1. Clean the series (sort, dedup, gap detection, stuck-value flagging)
      2. Detect excursions with debounce
      3. For each excursion: compute metrics, match rule, build Decision
      4. Compute leg-level MKT (returned via ExcursionWithDecision list context)

    Args:
        readings: Raw SensorReading list for this leg (may be unsorted/duplicated).
        rule_pack: Active RulePack for the cargo's regulatory regime.
        shipment_id: Parent shipment ID.
        leg_id: This leg's ID.
        cargo_description: Free-text cargo description for cargo-type rule matching.
        is_leg_complete: True if the leg has already completed (for detectedBeforeDelivery).
        delivery_eta: Projected delivery datetime for detectedBeforeDelivery flag.
        engine_version: Engine version string for Decision records.

    Returns:
        (excursions, gaps, sensor_suspect)
    """
    from datetime import datetime as _dt

    if engine_version is None:
        engine_version = settings.engine_version

    now = _dt.now(timezone.utc)

    # Step 1: clean
    cleaned = clean_series(
        readings,
        shipment_id=shipment_id,
        leg_id=leg_id,
        is_cold_chain=True,
    )

    # Step 2: detect excursion runs
    excursion_runs = detect_excursions(cleaned.readings, rule_pack)

    result_excursions: list[ExcursionWithDecision] = []

    for run_idx, run in enumerate(excursion_runs):
        oor_readings = [r for r in run
                        if r.temp_c > rule_pack.allowed_range_c.max
                        or r.temp_c < rule_pack.allowed_range_c.min]
        if not oor_readings:
            continue

        # Compute metrics
        started_at = oor_readings[0].timestamp
        last_oor = oor_readings[-1].timestamp
        # endedAt: None if still open (last reading is still out of range
        # or the series ends while still out of range)
        all_temps = [r.temp_c for r in run]
        last_run_reading = run[-1]
        is_still_open = (
            last_run_reading.temp_c > rule_pack.allowed_range_c.max
            or last_run_reading.temp_c < rule_pack.allowed_range_c.min
        )
        ended_at = None if is_still_open else last_oor

        dm = compute_degree_minutes(oor_readings, rule_pack.allowed_range_c.min, rule_pack.allowed_range_c.max)

        if len(oor_readings) >= 2:
            minutes_oor = (oor_readings[-1].timestamp - oor_readings[0].timestamp).total_seconds() / 60.0
        else:
            minutes_oor = 0.0

        is_freezing = any(r.temp_c < rule_pack.allowed_range_c.min for r in oor_readings)
        candidate = _ExcursionCandidate(oor_readings[0], rule_pack.allowed_range_c.min, rule_pack.allowed_range_c.max)
        for r in oor_readings[1:]:
            candidate.readings.append(r)
        peak_temp_c = candidate.actual_peak_temp_c

        # MKT over the full run (not just OOR readings)
        try:
            mkt = compute_mean_kinetic_temp_c([r.temp_c for r in run])
        except ValueError:
            mkt = sum(r.temp_c for r in run) / len(run)  # arithmetic mean fallback

        # Rule matching
        rule = match_rule(
            rule_pack,
            dm,
            minutes_oor,
            peak_temp_c,
            is_freezing,
            cargo_description,
        )

        if rule is None:
            # No rule matched — informational
            severity = Severity.informational
            rule_id = "NO-MATCH"
            citation = rule_pack.citation_base
        else:
            severity = rule.severity
            rule_id = rule.id
            citation = rule.citation

        # Disposition from rule pack map
        disposition_str = rule_pack.disposition_map.get(severity.value, "release")
        disposition = ExcursionDisposition(disposition_str)

        # detectedBeforeDelivery: True if leg not yet complete and delivery hasn't happened
        if is_leg_complete:
            detected_before_delivery = False
        elif delivery_eta is not None and now < delivery_eta:
            detected_before_delivery = True
        else:
            detected_before_delivery = not is_leg_complete

        # Evidence reading IDs
        evidence_ids = [r.reading_id for r in oor_readings]

        # door_open correlation: any OOR reading with door_open=True
        door_open_correlated = any(r.door_open is True for r in oor_readings)

        excursion = ExcursionModel(
            id=f"exc-{shipment_id}-{leg_id}-{run_idx:03d}",
            shipmentId=shipment_id,
            legId=leg_id,
            startedAt=started_at,
            endedAt=ended_at,
            peakTempC=peak_temp_c,
            minutesOutOfRange=int(minutes_oor),
            degreeMinutes=round(dm, 2),
            meanKineticTempC=round(mkt, 2),
            severity=severity,
            regulatoryBasis=f"{citation} — {'freeze' if is_freezing else 'heat'} excursion "
                            f"{minutes_oor:.0f}min, {dm:.1f} deg-min",
            disposition=disposition,
            evidenceReadingIds=evidence_ids,
            detectedBeforeDelivery=detected_before_delivery,
        )

        decision = Decision(
            rule_pack_id=rule_pack.id,
            rule_pack_version=rule_pack.version,
            rule_id=rule_id,
            citation=citation,
            inputs={
                "degree_minutes": round(dm, 2),
                "minutes_out_of_range": round(minutes_oor, 1),
                "peak_temp_c": round(peak_temp_c, 2),
                "is_freezing": int(is_freezing),
                "range_min_c": rule_pack.allowed_range_c.min,
                "range_max_c": rule_pack.allowed_range_c.max,
            },
            evidence_record_ids=evidence_ids,
            computed_at=now,
            engine_version=engine_version,
        )

        result_excursions.append(
            ExcursionWithDecision(
                excursion=excursion,
                decision=decision,
                data_gaps=cleaned.gaps,
                door_open_correlated=door_open_correlated,
                sensor_suspect=cleaned.sensor_suspect,
            )
        )

    return result_excursions, cleaned.gaps, cleaned.sensor_suspect
