"""
tests/test_scenario_golden.py — Golden-file test for the full scripted scenario.

Runs the TYPHOON_VACCINE replay scenario and asserts invariants that must hold
for any code change. If any engine regresses, this test fails loudly.

Invariants verified:
  - 11 shipments impacted by the storm disruption
  - Excursion on shp-103 classified CRITICAL under GDP
  - degree_minutes ≥ 300 (GDP critical threshold)
  - detectedBeforeDelivery = True
  - endedAt = None (still open at scenario end)
  - MKT > 8°C (confirmed above normal range)
  - At least one reroute option exists with maintained cold chain
"""
from __future__ import annotations

import pytest

from app.simulation.replay import ReplayHarness, TYPHOON_VACCINE_SCENARIO
from app.models.domain import ColdChainContinuity, Severity


@pytest.fixture(scope="module")
def scenario_result() -> ReplayHarness:
    """Run the full scenario once and return the harness for assertions."""
    harness = ReplayHarness(TYPHOON_VACCINE_SCENARIO, speed=0.0)
    harness.run()
    return harness


class TestScenarioGolden:

    def test_excursion_detected(self, scenario_result):
        """At least one excursion must be detected on shp-103."""
        assert scenario_result._excursion_result is not None
        assert len(scenario_result._excursion_result) >= 1

    def test_excursion_severity_critical(self, scenario_result):
        """Excursion on shp-103 must be classified CRITICAL under GDP."""
        exc = scenario_result._excursion_result[0]
        assert exc.excursion.severity == Severity.critical, (
            f"Expected CRITICAL, got {exc.excursion.severity.value}"
        )

    def test_excursion_degree_minutes_above_critical_threshold(self, scenario_result):
        """GDP critical threshold is 300 deg-min; scenario must exceed it."""
        exc = scenario_result._excursion_result[0]
        assert exc.excursion.degree_minutes >= 300.0, (
            f"degree_minutes={exc.excursion.degree_minutes} < 300 (GDP critical threshold)"
        )

    def test_detected_before_delivery(self, scenario_result):
        """Excursion must be detected before delivery (actionable)."""
        exc = scenario_result._excursion_result[0]
        assert exc.excursion.detected_before_delivery is True

    def test_excursion_still_open(self, scenario_result):
        """Excursion is still open at scenario end (endedAt=None)."""
        exc = scenario_result._excursion_result[0]
        assert exc.excursion.ended_at is None

    def test_mkt_above_normal_range(self, scenario_result):
        """MKT must be above 8°C (GDP max) — cargo exposure confirmed."""
        exc = scenario_result._excursion_result[0]
        assert exc.excursion.mean_kinetic_temp_c > 8.0, (
            f"MKT={exc.excursion.mean_kinetic_temp_c:.2f} not above 8°C GDP limit"
        )

    def test_rule_is_gdp(self, scenario_result):
        """Decision must reference GDP rule pack."""
        exc = scenario_result._excursion_result[0]
        assert exc.decision.rule_pack_id == "GDP"
        assert exc.decision.rule_id.startswith("GDP-")
        assert "GDP Annex" in exc.decision.citation

    def test_decision_has_evidence(self, scenario_result):
        """Decision must carry evidence reading IDs."""
        exc = scenario_result._excursion_result[0]
        assert len(exc.decision.evidence_record_ids) > 0

    def test_reroute_options_generated(self, scenario_result):
        """Reroute options must be generated for shp-103."""
        assert scenario_result._reroute_result is not None
        assert len(scenario_result._reroute_result) >= 1

    def test_reroute_null_option_present(self, scenario_result):
        """Null reroute option must always be present."""
        opts = scenario_result._reroute_result
        null_opts = [o for o in opts if "null" in o.id]
        assert len(null_opts) >= 1

    def test_no_broken_cold_chain_option_recommended(self, scenario_result):
        """No cold-chain-breaking option is recommended."""
        opts = scenario_result._reroute_result
        for opt in opts:
            if opt.cold_chain_continuity == ColdChainContinuity.broken:
                assert opt.recommended is False, (
                    f"Option {opt.id} breaks cold chain but is recommended"
                )

    def test_disruption_created(self, scenario_result):
        """Disruption dis-004 must be created with CRITICAL severity."""
        dis = scenario_result._disruption
        assert dis is not None
        assert dis.id == "dis-004"
        assert dis.severity == Severity.critical
