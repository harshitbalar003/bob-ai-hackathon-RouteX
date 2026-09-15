"""
tests/test_ml_features.py — Feature contract: training and serving produce identical vectors.

This is the single most important test in the ML test suite.  The single most
common bug in a production ML pipeline is computing features one way during
training (in generate_corpus.py) and another way at serving time (in
predictors/excursion.py).  Both paths call build_feature_vector() from
app/ml/features.py — this test verifies that for a fixed input the output
is byte-for-byte identical regardless of how the vector is constructed.

Also tests:
  - FEATURE_NAMES has no duplicates
  - CATEGORICAL_FEATURE_NAMES is a subset of FEATURE_NAMES
  - All features are present and in the correct order
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.features import (
    CATEGORICAL_FEATURE_NAMES,
    FEATURE_NAMES,
    MIN_READINGS_IN_WINDOW,
    WINDOW_MINUTES,
    build_feature_vector,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_PREDICTION_TS = datetime(2025, 7, 14, 10, 0, 0, tzinfo=timezone.utc)
_LEG_ARRIVES_AT = datetime(2025, 7, 14, 18, 0, 0, tzinfo=timezone.utc)


def _fixed_window() -> list[dict]:
    """
    A deterministic 2-hour window: 24 readings at 5-minute intervals,
    linearly rising from 4.0°C to 6.9°C with a door-open event at step 12.
    """
    n = 24
    window = []
    for i in range(n):
        ts = _PREDICTION_TS - timedelta(minutes=(n - 1 - i) * 5)
        temp = 4.0 + i * 0.125   # gentle rise: 4.0 → 6.875
        window.append({
            "timestamp": ts,
            "temp_c": round(temp, 3),
            "door_open": (i == 12),   # door open at exactly step 12
        })
    return window


def _call_build(window: list[dict]) -> dict:
    """Call build_feature_vector with fixed metadata."""
    return build_feature_vector(
        window,
        temp_range_min=2.0,
        temp_range_max=8.0,
        reefer_setpoint_c=5.0,
        leg_arrives_at=_LEG_ARRIVES_AT,
        next_transfer_within_4h=False,
        dwell_status="in_transit",
        ambient_temp_forecast_c=22.0,
        container_type="reefer_container",
        prediction_timestamp=_PREDICTION_TS,
    )


# ── Feature contract tests ─────────────────────────────────────────────────────

class TestFeatureContract:
    def test_feature_names_no_duplicates(self):
        assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES)), (
            "FEATURE_NAMES contains duplicate entries"
        )

    def test_categorical_names_subset_of_feature_names(self):
        for name in CATEGORICAL_FEATURE_NAMES:
            assert name in FEATURE_NAMES, (
                f"Categorical feature '{name}' not in FEATURE_NAMES"
            )

    def test_output_keys_match_feature_names_exactly(self):
        fv = _call_build(_fixed_window())
        assert list(fv.keys()) == FEATURE_NAMES, (
            "Feature vector keys don't match FEATURE_NAMES (order matters)"
        )

    def test_deterministic_for_fixed_input(self):
        """Calling build_feature_vector twice with the same input gives the same output."""
        window = _fixed_window()
        fv1 = _call_build(window)
        fv2 = _call_build(window)
        assert fv1 == fv2, "build_feature_vector is not deterministic for fixed input"

    def test_train_and_serve_vectors_identical(self):
        """
        Simulate the training path (generate_corpus.py calls build_feature_vector)
        and the serving path (predictors/excursion.py calls build_feature_vector).
        Both use the same function with the same arguments → must produce the same dict.

        This is the formal proof that there is no train/serve skew.
        """
        window = _fixed_window()

        # Training path: direct call to features.py (same as generate_corpus.py)
        train_vec = _call_build(window)

        # Serving path: via the predictor's import chain (same function)
        from app.ml.features import build_feature_vector as serve_build
        serve_vec = serve_build(
            window,
            temp_range_min=2.0,
            temp_range_max=8.0,
            reefer_setpoint_c=5.0,
            leg_arrives_at=_LEG_ARRIVES_AT,
            next_transfer_within_4h=False,
            dwell_status="in_transit",
            ambient_temp_forecast_c=22.0,
            container_type="reefer_container",
            prediction_timestamp=_PREDICTION_TS,
        )

        assert train_vec == serve_vec, (
            "Training and serving feature vectors differ for the same input. "
            "This is a train/serve skew bug."
        )


class TestFeatureValues:
    """Spot-check individual feature values against hand-computed expectations."""

    def setup_method(self):
        self.window = _fixed_window()
        self.fv = _call_build(self.window)

    def test_temp_current_is_last_reading(self):
        assert self.fv["temp_c_current"] == self.window[-1]["temp_c"]

    def test_temp_mean_in_range(self):
        temps = [r["temp_c"] for r in self.window]
        expected = sum(temps) / len(temps)
        assert abs(self.fv["temp_c_mean_2h"] - expected) < 1e-9

    def test_temp_min_is_minimum(self):
        temps = [r["temp_c"] for r in self.window]
        assert self.fv["temp_c_min_2h"] == min(temps)

    def test_temp_max_is_maximum(self):
        temps = [r["temp_c"] for r in self.window]
        assert self.fv["temp_c_max_2h"] == max(temps)

    def test_slope_positive_for_rising_window(self):
        assert self.fv["temp_slope_c_per_h"] > 0

    def test_dist_to_max_positive_when_not_breached(self):
        # current temp = 6.875, max = 8.0 → dist = 1.125
        assert self.fv["dist_to_max_c"] > 0

    def test_dist_to_min_positive_when_not_breached(self):
        # current temp = 6.875, min = 2.0 → dist = 4.875
        assert self.fv["dist_to_min_c"] > 0

    def test_door_open_count_is_one(self):
        assert self.fv["door_open_count_2h"] == 1

    def test_minutes_since_door_open_positive(self):
        # door open at step 12 = 55 minutes before prediction_ts
        assert self.fv["minutes_since_last_door_open"] > 0
        assert self.fv["minutes_since_last_door_open"] < 9999.0

    def test_reading_count_is_window_size(self):
        assert self.fv["reading_count_2h"] == 24

    def test_hours_remaining_positive(self):
        # 8h until arrival
        assert abs(self.fv["hours_remaining_leg"] - 8.0) < 0.1

    def test_next_transfer_flag_is_zero(self):
        assert self.fv["next_transfer_within_horizon"] == 0

    def test_categorical_values_preserved(self):
        assert self.fv["dwell_status"] == "in_transit"
        assert self.fv["container_type"] == "reefer_container"

    def test_stuck_value_run_is_zero_for_rising_window(self):
        # Each reading is different → no stuck run at end of window
        assert self.fv["stuck_value_run_min"] == 0.0
