"""
tests/test_ml_disabled.py — Verify ML_ENABLED=false leaves the app fully functional.

These tests assert the disabled path end-to-end:
  1. registry.startup(ml_enabled=False) → no models loaded
  2. predict_excursion_risk() → None (never raises)
  3. predict_breach_risk() → None (never raises)
  4. baseline_predict() still works (it is a pure function, not gated by ML_ENABLED)
  5. Prediction domain model is well-formed

No sklearn, no joblib — these must pass on any machine without ML deps.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.features import FEATURE_NAMES, baseline_predict, build_feature_vector
from app.ml.registry import MLRegistry
from app.ml.predictors.excursion import predict_breach_risk


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_window(n: int = 24, temp: float = 5.0) -> list[dict]:
    """Build a synthetic 2-hour trailing window (n readings, 5-min intervals)."""
    now = datetime(2025, 7, 14, 10, 0, 0, tzinfo=timezone.utc)
    return [
        {
            "timestamp": now - timedelta(minutes=(n - 1 - i) * 5),
            "temp_c": temp,
            "door_open": False,
        }
        for i in range(n)
    ]


def _make_fv(temp: float = 5.0) -> dict:
    window = _make_window(24, temp)
    return build_feature_vector(
        window,
        temp_range_min=2.0,
        temp_range_max=8.0,
        reefer_setpoint_c=5.0,
        leg_arrives_at=datetime(2025, 7, 14, 18, 0, 0, tzinfo=timezone.utc),
        next_transfer_within_4h=False,
        dwell_status="in_transit",
        ambient_temp_forecast_c=22.0,
        container_type="reefer_container",
        prediction_timestamp=datetime(2025, 7, 14, 10, 0, 0, tzinfo=timezone.utc),
    )


# ── Registry disabled path ────────────────────────────────────────────────────

class TestMLRegistryDisabled:
    def test_startup_disabled_loads_no_models(self):
        reg = MLRegistry()
        reg.startup(ml_enabled=False)
        assert not reg.is_enabled()
        assert reg.model_cards() == []

    def test_predict_excursion_risk_returns_none_when_disabled(self):
        reg = MLRegistry()
        reg.startup(ml_enabled=False)
        fv = _make_fv()
        result = reg.predict_excursion_risk(fv)
        assert result is None

    def test_predict_excursion_risk_never_raises(self):
        """Even with a malformed feature vector, None is returned, never an exception."""
        reg = MLRegistry()
        reg.startup(ml_enabled=False)
        result = reg.predict_excursion_risk({})
        assert result is None

    def test_startup_with_nonexistent_dir_disables_ml(self, tmp_path):
        import pathlib
        reg = MLRegistry()
        reg.startup(ml_enabled=True, artifacts_dir=tmp_path / "nonexistent")
        assert not reg.is_enabled()


# ── Predictor disabled path ───────────────────────────────────────────────────

class TestExcursionPredictorDisabled:
    def test_returns_none_when_ml_disabled(self):
        """
        predict_breach_risk returns None when the module-level registry has no
        models loaded (ML_ENABLED=false state).
        """
        # The module-level registry is initialised with ml_enabled=False by default
        # (no startup() called at import time). Force the disabled state.
        from app.ml.registry import registry
        # Ensure no models are present (clean slate for this test)
        registry._models.clear()
        registry._enabled = False

        window = _make_window(24)
        result = predict_breach_risk(
            window_readings=window,
            shipment_id="shp-101",
            leg_id="leg-101-1",
            temp_range_min=2.0,
            temp_range_max=8.0,
            reefer_setpoint_c=5.0,
            leg_arrives_at=datetime(2025, 7, 14, 18, 0, 0, tzinfo=timezone.utc),
            next_transfer_within_4h=False,
            dwell_status="in_transit",
            ambient_temp_forecast_c=22.0,
            container_type="reefer_container",
        )
        assert result is None

    def test_returns_none_when_too_few_readings(self):
        """Fewer than MIN_READINGS_IN_WINDOW → None, no model call attempted."""
        from app.ml.features import MIN_READINGS_IN_WINDOW
        window = _make_window(MIN_READINGS_IN_WINDOW - 1)
        result = predict_breach_risk(
            window_readings=window,
            shipment_id="shp-101",
            leg_id="leg-101-1",
            temp_range_min=2.0,
            temp_range_max=8.0,
            reefer_setpoint_c=5.0,
            leg_arrives_at=datetime(2025, 7, 14, 18, 0, 0, tzinfo=timezone.utc),
            next_transfer_within_4h=False,
            dwell_status="in_transit",
            ambient_temp_forecast_c=22.0,
            container_type="reefer_container",
        )
        assert result is None


# ── Feature engineering (not gated by ML_ENABLED) ────────────────────────────

class TestFeatureEngineering:
    def test_build_feature_vector_returns_all_features(self):
        fv = _make_fv()
        assert set(fv.keys()) == set(FEATURE_NAMES)

    def test_feature_names_order_matches_constant(self):
        """Keys must match FEATURE_NAMES exactly (order matters for the model)."""
        fv = _make_fv()
        assert list(fv.keys()) == FEATURE_NAMES

    def test_dist_to_max_negative_when_breached(self):
        """dist_to_max_c is negative when temp is above range_max."""
        window = _make_window(24, temp=9.5)  # above max=8.0
        fv = build_feature_vector(
            window,
            temp_range_min=2.0,
            temp_range_max=8.0,
            reefer_setpoint_c=5.0,
            leg_arrives_at=datetime(2025, 7, 14, 18, 0, 0, tzinfo=timezone.utc),
            next_transfer_within_4h=False,
            dwell_status="in_transit",
            ambient_temp_forecast_c=22.0,
            container_type="reefer_container",
            prediction_timestamp=datetime(2025, 7, 14, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert fv["dist_to_max_c"] < 0

    def test_no_door_event_gives_sentinel(self):
        fv = _make_fv(5.0)
        from app.ml.features import SENTINEL_NO_DOOR_EVENT
        assert fv["minutes_since_last_door_open"] == SENTINEL_NO_DOOR_EVENT

    def test_stuck_value_detected(self):
        """A window of identical readings → stuck_value_run_min > 0."""
        fv = _make_fv(5.0)  # all readings are 5.0 → stuck run = full window
        assert fv["stuck_value_run_min"] > 0

    def test_slope_positive_for_rising_temps(self):
        """A window where temperature rises monotonically → positive slope."""
        now = datetime(2025, 7, 14, 10, 0, 0, tzinfo=timezone.utc)
        window = [
            {
                "timestamp": now - timedelta(minutes=(23 - i) * 5),
                "temp_c": 2.0 + i * 0.2,   # rising from 2.0 to 6.6
                "door_open": False,
            }
            for i in range(24)
        ]
        fv = build_feature_vector(
            window,
            temp_range_min=2.0,
            temp_range_max=8.0,
            reefer_setpoint_c=5.0,
            leg_arrives_at=datetime(2025, 7, 14, 18, 0, 0, tzinfo=timezone.utc),
            next_transfer_within_4h=False,
            dwell_status="in_transit",
            ambient_temp_forecast_c=22.0,
            container_type="reefer_container",
            prediction_timestamp=datetime(2025, 7, 14, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert fv["temp_slope_c_per_h"] > 0


# ── Baseline heuristic (pure function, no ML deps) ────────────────────────────

class TestBaselinePredict:
    def test_predicts_breach_when_slope_extrapolates_above_max(self):
        """Rising temp that will cross max → baseline = 1."""
        fv = _make_fv(7.5)   # close to max=8.0
        # Manually set a steep slope
        fv["temp_slope_c_per_h"] = 1.0
        fv["dist_to_max_c"] = 0.5   # 0.5°C below max
        fv["dist_to_min_c"] = 5.5
        # projected in 4h = 7.5 + 4.0 = 11.5 > 8.0 → breach
        fv["temp_c_current"] = 7.5
        assert baseline_predict(fv) == 1

    def test_no_breach_predicted_when_stable(self):
        """Stable temp well within range → baseline = 0."""
        fv = _make_fv(5.0)
        fv["temp_slope_c_per_h"] = 0.0
        assert baseline_predict(fv) == 0
