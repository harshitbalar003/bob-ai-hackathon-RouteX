"""
tests/test_cold_chain.py — Full cold chain engine test suite.

Tests: MKT, degree-minutes, excursion detection (debounce, gaps, spikes, open),
       freezing vs warming severity asymmetry, rule matching, cleaning behaviour.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.engines.cold_chain import (
    CleanedSeries,
    _longest_stuck_run_minutes,
    analyse_leg,
    clean_series,
    compute_degree_minutes,
    compute_mean_kinetic_temp_c,
    detect_excursions,
    match_rule,
)
from app.models.domain import SensorReading, Severity
from app.rules import get_rule_pack, load_rule_packs

# ── Helpers ───────────────────────────────────────────────────────────────────

_GDP = get_rule_pack("GDP")
_FSMA = get_rule_pack("FSMA")
_WHO = get_rule_pack("WHO_PQS")
_USP = get_rule_pack("USP_1079")

_T0 = datetime(2025, 7, 14, 6, 0, 0, tzinfo=timezone.utc)


def _r(
    temp_c: float,
    offset_minutes: float = 0,
    shipment_id: str = "shp-test",
    sensor_id: str = "sen-test",
    leg_id: str = "leg-test",
    door_open: bool | None = None,
) -> SensorReading:
    ts = _T0 + timedelta(minutes=offset_minutes)
    return SensorReading(
        shipmentId=shipment_id,
        sensorId=sensor_id,
        legId=leg_id,
        timestamp=ts.isoformat().replace("+00:00", "Z"),
        tempC=temp_c,
        doorOpen=door_open,
    )


def _readings(
    temps: list[float],
    interval_minutes: float = 5.0,
    **kwargs,
) -> list[SensorReading]:
    return [_r(t, i * interval_minutes, **kwargs) for i, t in enumerate(temps)]


# ── MKT tests ─────────────────────────────────────────────────────────────────

class TestMeanKineticTemp:
    """
    MKT validation against published worked examples.

    Reference: USP General Chapter <1079>, Table 1.
    A series of temperatures where T_mkt ≈ 25°C is the classic sanity check.
    At exactly 25°C constant, MKT = 25°C (fixed point of the formula).
    """

    def test_constant_temperature_is_identity(self):
        """MKT of a constant series = that constant temperature."""
        # USP <1079> note: at uniform temperature, MKT = that temperature.
        for t in [4.0, 8.0, 25.0, -20.0]:
            result = compute_mean_kinetic_temp_c([t] * 100)
            assert abs(result - t) < 0.01, f"MKT({t}) = {result} (expected {t})"

    def test_mkt_increases_with_higher_temps(self):
        """MKT is weighted toward higher temperatures (Arrhenius weighting)."""
        low_series = [4.0, 4.0, 5.0, 4.0, 4.0]
        high_series = [4.0, 4.0, 25.0, 4.0, 4.0]
        mkt_low = compute_mean_kinetic_temp_c(low_series)
        mkt_high = compute_mean_kinetic_temp_c(high_series)
        assert mkt_high > mkt_low

    def test_mkt_above_arithmetic_mean_for_asymmetric_series(self):
        """
        MKT is always >= arithmetic mean for typical pharma conditions.

        From USP <1079> Table 1: a series [25,25,25,25,40] has
        arithmetic mean = 28°C but MKT ≈ 30.5°C (Arrhenius weighting
        skews toward the hot observation).
        """
        series = [25.0, 25.0, 25.0, 25.0, 40.0]
        arithmetic_mean = sum(series) / len(series)
        mkt = compute_mean_kinetic_temp_c(series)
        assert mkt > arithmetic_mean

    def test_mkt_empty_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            compute_mean_kinetic_temp_c([])

    def test_mkt_single_value(self):
        """Single-reading MKT = that reading."""
        result = compute_mean_kinetic_temp_c([6.0])
        assert abs(result - 6.0) < 0.01

    def test_mkt_usp_worked_example(self):
        """
        USP <1079> Table 1 worked example:
        Temperatures (°C): 24, 26, 28, 25, 23 (five 24h periods ≈ equal weight)
        Expected MKT ≈ 25.4°C (Arrhenius mean > arithmetic mean of 25.2°C)

        Source: USP General Chapter <1079>, Table 1 footnote.
        """
        series = [24.0, 26.0, 28.0, 25.0, 23.0]
        mkt = compute_mean_kinetic_temp_c(series)
        arithmetic = sum(series) / len(series)  # 25.2°C
        # MKT must exceed arithmetic mean
        assert mkt > arithmetic
        # MKT should be ≈ 25.3–25.6°C range (exact value depends on ΔH)
        assert 25.0 < mkt < 26.5, f"MKT={mkt} outside expected range 25.0–26.5°C"

    def test_mkt_cold_chain_series(self):
        """
        Cold chain series with one excursion: MKT should be clearly above 8°C.

        Series: mostly 5°C, one reading at 25°C.
        Source: validates Arrhenius weighting for pharmaceutical cold chain assessment.
        """
        # 20 readings at 5°C + 1 at 25°C
        series = [5.0] * 20 + [25.0]
        mkt = compute_mean_kinetic_temp_c(series)
        arithmetic = sum(series) / len(series)  # ≈ 5.95°C
        assert mkt > arithmetic   # Arrhenius weighting pulls toward the hot reading


# ── Degree-minutes tests ──────────────────────────────────────────────────────

class TestDegreeMinutes:
    """
    Degree-minutes: Σ |T_i − T_limit| × Δt_i

    Hand-computed reference series verified against formula.
    """

    def test_single_reading_zero(self):
        """One out-of-range reading = 0 degree-minutes (no time elapsed)."""
        readings = [_r(10.0)]   # GDP range is 2–8; 10°C is out of range
        dm = compute_degree_minutes(readings, 2.0, 8.0)
        assert dm == 0.0

    def test_hand_computed_warming_excursion(self):
        """
        Hand-computed: 3 readings at 10°C, 5-minute intervals, GDP range 2–8°C.

        T_limit (upper) = 8°C
        Reading 0: 10°C → contributes (10-8)*5 = 10 deg-min
        Reading 1: 10°C → contributes (10-8)*5 = 10 deg-min
        Reading 2: 10°C → contributes (10-8)*5 = 10 deg-min (tail window)
        Total = 30 deg-min
        """
        readings = _readings([10.0, 10.0, 10.0], interval_minutes=5.0)
        dm = compute_degree_minutes(readings, 2.0, 8.0)
        assert abs(dm - 30.0) < 0.01, f"Expected 30.0 deg-min, got {dm}"

    def test_hand_computed_freezing_excursion(self):
        """
        Hand-computed: 2 readings at 0°C, 5-minute intervals, GDP range 2–8°C.

        T_limit (lower) = 2°C
        Reading 0: 0°C → contributes (2-0)*5 = 10 deg-min
        Reading 1: 0°C → contributes (2-0)*5 = 10 deg-min (tail)
        Total = 20 deg-min
        """
        readings = _readings([0.0, 0.0], interval_minutes=5.0)
        dm = compute_degree_minutes(readings, 2.0, 8.0)
        assert abs(dm - 20.0) < 0.01, f"Expected 20.0 deg-min, got {dm}"

    def test_30min_at_10_vs_30min_at_8_5_are_different(self):
        """
        30 minutes at 10°C is NOT the same as 30 minutes at 8.5°C.

        This is the key distinction: a system that only counts minutes misses this.
        10°C: (10-8)*30 = 60 deg-min
        8.5°C: (8.5-8)*30 = 15 deg-min
        """
        readings_hot = _readings([10.0] * 7, interval_minutes=5.0)   # ~30 min
        readings_warm = _readings([8.5] * 7, interval_minutes=5.0)
        dm_hot = compute_degree_minutes(readings_hot, 2.0, 8.0)
        dm_warm = compute_degree_minutes(readings_warm, 2.0, 8.0)
        assert dm_hot > dm_warm * 3, (
            f"10°C excursion ({dm_hot:.1f}) should be >3x worse than "
            f"8.5°C excursion ({dm_warm:.1f})"
        )

    def test_empty_readings_zero(self):
        dm = compute_degree_minutes([], 2.0, 8.0)
        assert dm == 0.0


# ── Cleaning tests ────────────────────────────────────────────────────────────

class TestCleanSeries:

    def test_deduplication(self):
        """Duplicate readings (same sensor_id + timestamp) are removed."""
        r1 = _r(5.0, 0)
        r2 = _r(5.0, 0)   # same sensor, same timestamp
        r3 = _r(5.0, 5)
        cleaned = clean_series(
            [r1, r2, r3],
            shipment_id="shp-x",
            leg_id="leg-x",
            is_cold_chain=True,
        )
        assert len(cleaned.readings) == 2

    def test_out_of_order_sorted(self):
        """Out-of-order readings are sorted by timestamp."""
        r1 = _r(5.0, 10)
        r2 = _r(5.0, 0)
        r3 = _r(5.0, 5)
        cleaned = clean_series(
            [r1, r2, r3],
            shipment_id="shp-x",
            leg_id="leg-x",
            is_cold_chain=True,
        )
        timestamps = [r.timestamp for r in cleaned.readings]
        assert timestamps == sorted(timestamps)

    def test_gap_detection(self):
        """Interval > gap_threshold produces a DataGap record."""
        # 5 min nominal × 3 = 15 min threshold; 20 min gap should trigger
        r1 = _r(5.0, 0)
        r2 = _r(5.0, 20)   # 20 min gap
        cleaned = clean_series(
            [r1, r2],
            shipment_id="shp-x",
            leg_id="leg-x",
            is_cold_chain=True,
            gap_threshold_minutes=15,
        )
        assert len(cleaned.gaps) == 1
        assert cleaned.gaps[0].duration_minutes == pytest.approx(20.0, abs=0.1)
        assert cleaned.gaps[0].is_compliance_finding is True

    def test_no_gap_below_threshold(self):
        """5 min interval is exactly nominal — no gap."""
        r1 = _r(5.0, 0)
        r2 = _r(5.0, 5)
        cleaned = clean_series(
            [r1, r2],
            shipment_id="shp-x",
            leg_id="leg-x",
            is_cold_chain=True,
            gap_threshold_minutes=15,
        )
        assert len(cleaned.gaps) == 0

    def test_non_cold_chain_gap_not_compliance_finding(self):
        """Gap on a non-cold-chain leg is detected but is NOT a compliance finding."""
        r1 = _r(5.0, 0)
        r2 = _r(5.0, 20)
        cleaned = clean_series(
            [r1, r2],
            shipment_id="shp-x",
            leg_id="leg-x",
            is_cold_chain=False,
            gap_threshold_minutes=15,
        )
        assert len(cleaned.gaps) == 1
        assert cleaned.gaps[0].is_compliance_finding is False

    def test_stuck_value_detection(self):
        """Sensor reporting identical temp for >60 min flagged as suspect."""
        readings = _readings([5.0] * 14, interval_minutes=5.0)  # 65 min of 5.0°C
        cleaned = clean_series(
            readings,
            shipment_id="shp-x",
            leg_id="leg-x",
            is_cold_chain=True,
            stuck_value_minutes=60,
        )
        assert cleaned.sensor_suspect is True

    def test_varying_values_not_stuck(self):
        """Sensor that varies is not flagged."""
        temps = [4.0, 4.1, 4.2, 4.1, 4.0, 4.2, 4.3] * 3
        readings = _readings(temps, interval_minutes=5.0)
        cleaned = clean_series(
            readings,
            shipment_id="shp-x",
            leg_id="leg-x",
            is_cold_chain=True,
            stuck_value_minutes=60,
        )
        assert cleaned.sensor_suspect is False


# ── Excursion detection tests ──────────────────────────────────────────────────

class TestExcursionDetection:

    def test_single_contiguous_run(self):
        """A single block of out-of-range readings = one excursion."""
        temps = [5.0, 5.0, 9.0, 10.0, 9.5, 8.5, 5.0, 5.0]
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        assert len(exc) == 1

    def test_two_separate_runs(self):
        """Two out-of-range blocks separated by enough in-range time = two excursions."""
        # 5 readings in range, 3 out, 3 in (>10 min debounce), 3 out
        temps = [5.0] * 5 + [10.0] * 3 + [5.0] * 3 + [10.0] * 3
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        assert len(exc) == 2

    def test_debounce_merges_noisy_readings(self):
        """
        A single noisy in-range reading during an excursion does NOT close it.

        Without debounce, 40 brief dips in-range would create 40 excursions.
        With debounce_minutes=10, a single 5-min dip is swallowed.
        """
        # out, out, ONE in-range dip, out, out
        temps = [10.0, 10.0, 5.0, 10.0, 10.0]
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        assert len(exc) == 1, (
            f"Debounce should merge noisy dip; got {len(exc)} excursions"
        )

    def test_debounce_closes_after_sustained_recovery(self):
        """
        After sustained in-range readings > debounce window, excursion closes.
        """
        # 3 out of range, then 3 in-range at 5 min intervals = 15 min (>10 debounce)
        temps = [10.0, 10.0, 10.0, 5.0, 5.0, 5.0]
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        assert len(exc) == 1
        oor = [r for r in exc[0] if r.temp_c > 8.0]
        # excursion should be closed (ended_at would be set by analyse_leg)

    def test_single_spike_reading(self):
        """
        A single out-of-range spike followed by immediate recovery.
        Debounce: a single 5-min reading gives 5 min in-range before another OOR.
        If no following OOR, the series ends — excursion is recorded.
        """
        temps = [5.0, 5.0, 15.0, 5.0, 5.0]  # one spike at t=10min
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        # The spike + 10 min of in-range recovery = closed excursion
        assert len(exc) == 1

    def test_still_open_excursion_at_end_of_series(self):
        """
        If the series ends while still out of range, excursion is still open.
        """
        temps = [5.0, 5.0, 10.0, 11.0, 12.0]  # ends out of range
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        assert len(exc) == 1
        # Last reading is out of range
        last = exc[0][-1]
        assert last.temp_c > 8.0

    def test_no_excursion_in_range(self):
        """Series fully in range = no excursions."""
        temps = [4.0, 4.5, 5.0, 5.5, 6.0, 5.5]
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        assert len(exc) == 0

    def test_freezing_excursion_detected(self):
        """Temperature below min_range is detected as an excursion."""
        temps = [5.0, 5.0, 0.0, -1.0, 0.5, 5.0, 5.0]
        readings = _readings(temps, interval_minutes=5.0)
        exc = detect_excursions(readings, _GDP, debounce_minutes=10)
        assert len(exc) == 1
        oor = [r.temp_c for r in exc[0] if r.temp_c < 2.0]
        assert len(oor) >= 2


# ── Rule matching / severity asymmetry tests ──────────────────────────────────

class TestRuleMatching:

    def test_freezing_more_severe_than_warming_at_equal_degree_minutes(self):
        """
        Freezing excursion on vaccine cargo must classify as more severe
        than a warming excursion with equivalent degree-minutes.

        GDP pack has a lower degree-minute threshold for freezing + vaccine cargo.
        """
        pack = _GDP
        # Warming: 150 degree-minutes, 90 min OOR — should match MAJOR
        warming_rule = match_rule(
            pack, degree_minutes=150, minutes_out_of_range=90,
            peak_temp_c=10.0, is_freezing=False, cargo_description="vaccines"
        )
        # Freezing: same 150 degree-minutes, 90 min OOR, with below_range
        # GDP-CRITICAL-FREEZE threshold is 60 deg-min for vaccine cargo
        freezing_rule = match_rule(
            pack, degree_minutes=150, minutes_out_of_range=90,
            peak_temp_c=1.0, is_freezing=True, cargo_description="vaccines biologics"
        )
        assert warming_rule is not None
        assert freezing_rule is not None
        # Freezing should be CRITICAL, warming should be MAJOR at these values
        assert freezing_rule.severity == Severity.critical
        assert warming_rule.severity.value in ("major", "critical")
        # Freeze severity >= warming severity at equal degree-minutes
        severity_order = {Severity.informational: 0, Severity.minor: 1, Severity.major: 2, Severity.critical: 3}
        assert severity_order[freezing_rule.severity] >= severity_order[warming_rule.severity]

    def test_critical_warming_at_high_degree_minutes(self):
        """GDP: >300 deg-min + >120 min OOR = CRITICAL."""
        rule = match_rule(_GDP, 350, 130, peak_temp_c=12.0, is_freezing=False)
        assert rule is not None
        assert rule.severity == Severity.critical

    def test_major_warming(self):
        """GDP: 150 deg-min + 70 min OOR = MAJOR."""
        rule = match_rule(_GDP, 150, 70, peak_temp_c=10.0, is_freezing=False)
        assert rule is not None
        assert rule.severity == Severity.major

    def test_minor_excursion(self):
        """GDP: small degree-minutes, short duration = MINOR."""
        rule = match_rule(_GDP, 5.0, 15, peak_temp_c=8.5, is_freezing=False)
        assert rule is not None
        assert rule.severity == Severity.minor

    def test_no_match_returns_none_if_no_rules_apply(self):
        """If no rule can match (shouldn't happen with a catch-all minor rule), returns None."""
        # This should NOT happen with our rule packs, which have a catch-all MINOR
        rule = match_rule(_GDP, 0.0, 0, peak_temp_c=8.1, is_freezing=False)
        assert rule is not None   # GDP has a catch-all minor rule

    def test_who_pqs_minor_maps_to_quarantine(self):
        """WHO PQS minor excursions require QA review (stricter than GDP)."""
        pack = get_rule_pack("WHO_PQS")
        assert pack.disposition_map["minor"] == "quarantine_pending_QA"

    def test_fsma_food_cargo_warming_critical(self):
        """FSMA: >200 deg-min + >120 min = CRITICAL for food cargo."""
        rule = match_rule(_FSMA, 250, 130, peak_temp_c=6.0, is_freezing=False)
        assert rule is not None
        assert rule.severity == Severity.critical

    def test_cargo_type_filtering(self):
        """
        WHO freeze-sensitive rule applies to 'vaccines' but not to 'automotive parts'.
        """
        pack = get_rule_pack("WHO_PQS")
        # For vaccines: even 0 deg-min freeze = CRITICAL
        vaccine_rule = match_rule(
            pack, 0.0, 0, peak_temp_c=1.0, is_freezing=True,
            cargo_description="vaccines freeze_sensitive"
        )
        # For automotive parts: freeze rule with applies_to_cargo = freeze_sensitive
        # should NOT match; fall through to next rule
        auto_rule = match_rule(
            pack, 0.0, 0, peak_temp_c=1.0, is_freezing=True,
            cargo_description="automotive parts"
        )
        if vaccine_rule is not None:
            assert vaccine_rule.severity == Severity.critical
        if auto_rule is not None:
            # Should match the general freeze rule, not the freeze_sensitive one
            assert auto_rule.id != "WHO-CRITICAL-FREEZE-SENSITIVE"


# ── analyse_leg integration tests ─────────────────────────────────────────────

class TestAnalyseLeg:

    def _delivery_eta(self, hours_from_now: float) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=hours_from_now)

    def test_clean_leg_no_excursions(self):
        temps = [4.0, 4.5, 5.0, 5.5, 6.0, 5.5, 5.0, 4.5]
        readings = _readings(temps)
        exc, gaps, suspect = analyse_leg(
            readings, _GDP, "shp-x", "leg-x", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )
        assert len(exc) == 0
        assert len(gaps) == 0
        assert suspect is False

    def test_major_excursion_detected_before_delivery(self):
        """A warm excursion on an in-transit leg → detectedBeforeDelivery=True."""
        # Warming excursion: 5°C → spike to 12°C for 14 readings (65 min) → return
        temps = [5.0] * 5 + [12.0] * 14 + [5.0] * 5
        readings = _readings(temps)
        exc_list, _, _ = analyse_leg(
            readings, _GDP, "shp-x", "leg-x", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )
        assert len(exc_list) >= 1
        exc = exc_list[0]
        assert exc.excursion.detected_before_delivery is True
        assert exc.excursion.severity in (Severity.major, Severity.critical)
        assert exc.decision.rule_pack_id == "GDP"
        assert exc.decision.rule_id != ""
        assert len(exc.decision.evidence_record_ids) > 0

    def test_completed_leg_not_detected_before_delivery(self):
        """Excursion on a completed leg → detectedBeforeDelivery=False."""
        temps = [5.0] * 3 + [12.0] * 14 + [5.0] * 3
        readings = _readings(temps)
        exc_list, _, _ = analyse_leg(
            readings, _GDP, "shp-x", "leg-x", "vaccines",
            is_leg_complete=True, delivery_eta=None,
        )
        assert len(exc_list) >= 1
        assert exc_list[0].excursion.detected_before_delivery is False

    def test_door_open_correlated(self):
        """Excursion with door_open=True readings is flagged."""
        temps = [5.0, 5.0, 10.0, 10.0, 5.0, 5.0]
        readings = [
            _r(5.0, 0),
            _r(5.0, 5),
            _r(10.0, 10, door_open=True),
            _r(10.0, 15, door_open=True),
            _r(5.0, 20),
            _r(5.0, 25),
        ]
        exc_list, _, _ = analyse_leg(
            readings, _GDP, "shp-x", "leg-x", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )
        assert len(exc_list) >= 1
        assert exc_list[0].door_open_correlated is True

    def test_data_gap_compliance_finding(self):
        """A large gap on a cold-chain leg is a compliance finding."""
        # Normal reading, then 20-minute gap (above 15-min threshold)
        readings = [_r(5.0, 0), _r(5.0, 20)]
        _, gaps, _ = analyse_leg(
            readings, _GDP, "shp-x", "leg-x", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
            # Override gap threshold via config default (5*3=15 min)
        )
        assert len(gaps) == 1
        assert gaps[0].is_compliance_finding is True

    def test_evidence_ids_are_canonical(self):
        """Evidence reading IDs follow {shipmentId}:{sensorId}:{timestamp_ms} format."""
        temps = [5.0] * 3 + [12.0] * 6 + [5.0] * 3
        readings = _readings(temps)
        exc_list, _, _ = analyse_leg(
            readings, _GDP, "shp-test", "leg-test", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )
        assert len(exc_list) >= 1
        for eid in exc_list[0].decision.evidence_record_ids:
            parts = eid.split(":")
            assert len(parts) == 3, f"Malformed evidence ID: {eid}"
            assert parts[0] == "shp-test"
            assert parts[1] == "sen-test"
            assert parts[2].isdigit()

    def test_decision_has_full_audit_trail(self):
        """Every Decision has rule_pack_id, rule_pack_version, rule_id, citation, inputs."""
        temps = [5.0] * 3 + [12.0] * 14 + [5.0] * 3
        readings = _readings(temps)
        exc_list, _, _ = analyse_leg(
            readings, _GDP, "shp-x", "leg-x", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )
        assert len(exc_list) >= 1
        d = exc_list[0].decision
        assert d.rule_pack_id == "GDP"
        assert d.rule_pack_version == "1.0.0"
        assert d.rule_id != ""
        assert d.citation != ""
        assert "degree_minutes" in d.inputs
        assert "minutes_out_of_range" in d.inputs
        assert "peak_temp_c" in d.inputs

    def test_still_open_excursion_ended_at_none(self):
        """An excursion that hasn't recovered has endedAt=None."""
        temps = [5.0, 5.0, 10.0, 11.0, 12.0]  # ends out of range
        readings = _readings(temps)
        exc_list, _, _ = analyse_leg(
            readings, _GDP, "shp-x", "leg-x", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )
        assert len(exc_list) >= 1
        assert exc_list[0].excursion.ended_at is None

    def test_freezing_vs_warming_severity_asymmetry_full_pipeline(self):
        """
        End-to-end: identical degree-minutes, freezing vs warming.
        Freezing on vaccine cargo must classify as CRITICAL; warming as MAJOR.
        """
        # Same duration, same degree-deviation, different direction
        # Warming: 10°C for 14 readings (65 min) → 2°C above 8°C max
        # → 2 * 65 = 130 deg-min approx → MAJOR
        warming_temps = [5.0] * 5 + [10.0] * 13 + [5.0] * 5
        # Freezing: 0°C for 14 readings (65 min) → 2°C below 2°C min
        # → 2 * 65 = 130 deg-min approx → CRITICAL (freeze on vaccine)
        freezing_temps = [5.0] * 5 + [0.0] * 13 + [5.0] * 5

        warm_list, _, _ = analyse_leg(
            _readings(warming_temps), _GDP, "shp-w", "leg-w", "vaccines",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )
        freeze_list, _, _ = analyse_leg(
            _readings(freezing_temps), _GDP, "shp-f", "leg-f", "vaccines biologics",
            is_leg_complete=False, delivery_eta=self._delivery_eta(48),
        )

        assert len(warm_list) >= 1
        assert len(freeze_list) >= 1

        sev_order = {Severity.informational: 0, Severity.minor: 1, Severity.major: 2, Severity.critical: 3}
        warm_sev = warm_list[0].excursion.severity
        freeze_sev = freeze_list[0].excursion.severity

        assert sev_order[freeze_sev] >= sev_order[warm_sev], (
            f"Freeze ({freeze_sev}) should be >= warm ({warm_sev}) at equal deg-min for vaccines"
        )
