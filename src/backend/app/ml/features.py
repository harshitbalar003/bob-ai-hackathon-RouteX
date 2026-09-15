"""
app/ml/features.py — Shared feature engineering for Model 1 (Excursion Forecaster).

THIS IS THE SINGLE CODE PATH FOR BOTH TRAINING AND INFERENCE.

The single most common bug in ML pipelines is computing features one way
during training and another way at serving time.  This module is imported by:
  - app/ml/generate_corpus.py  (training)
  - app/ml/predictors/excursion.py  (inference)

Both paths call build_feature_vector() with the same inputs and get the same
output.  A test in tests/test_ml_features.py asserts this for a fixed window.

Feature list (18 features for Model 1):
  1.  temp_c_current             — instantaneous temperature
  2.  temp_c_mean_2h             — rolling mean over 2-hour window
  3.  temp_c_min_2h              — rolling minimum
  4.  temp_c_max_2h              — rolling maximum
  5.  temp_slope_c_per_h         — linear trend (OLS); the baseline predictor
  6.  temp_variance_2h           — rolling variance
  7.  dist_to_max_c              — range_max − current; negative if breached
  8.  dist_to_min_c              — current − range_min; negative if breached
  9.  minutes_since_last_door_open — 9999.0 if no door event in window
  10. door_open_count_2h         — cumulative door-open events in window
  11. dwell_status               — categorical: 'in_transit'|'dwell'|'transfer'
  12. ambient_temp_forecast_c    — ambient at current position
  13. container_type             — categorical: asset type string
  14. reefer_setpoint_c          — refrigeration setpoint
  15. hours_remaining_leg        — hours left on current leg
  16. next_transfer_within_horizon — bool (1/0): transfer scheduled in < 4h
  17. reading_count_2h           — number of readings in window (gap indicator)
  18. stuck_value_run_min        — minutes sensor has reported identical value

Categorical features (passed as pandas 'category' dtype to HistGradientBoosting):
  - dwell_status
  - container_type
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence


# ── Constants ─────────────────────────────────────────────────────────────────

WINDOW_MINUTES = 120          # 2-hour trailing window
HORIZON_HOURS = 4.0           # prediction horizon
MIN_READINGS_IN_WINDOW = 12   # 60% of expected 24 readings; fewer → skip row
SENTINEL_NO_DOOR_EVENT = 9999.0  # used when no door event in window

# Ordered feature names — the contract between training and serving.
# Changing this list requires a model version bump.
FEATURE_NAMES: list[str] = [
    "temp_c_current",
    "temp_c_mean_2h",
    "temp_c_min_2h",
    "temp_c_max_2h",
    "temp_slope_c_per_h",
    "temp_variance_2h",
    "dist_to_max_c",
    "dist_to_min_c",
    "minutes_since_last_door_open",
    "door_open_count_2h",
    "dwell_status",
    "ambient_temp_forecast_c",
    "container_type",
    "reefer_setpoint_c",
    "hours_remaining_leg",
    "next_transfer_within_horizon",
    "reading_count_2h",
    "stuck_value_run_min",
]

CATEGORICAL_FEATURE_NAMES: list[str] = ["dwell_status", "container_type"]


# ── Window helpers ─────────────────────────────────────────────────────────────

def _ols_slope(times_min: list[float], temps: list[float]) -> float:
    """
    Compute OLS linear regression slope (°C / hour) over (time, temp) pairs.

    Returns 0.0 if fewer than 2 points.
    """
    n = len(times_min)
    if n < 2:
        return 0.0
    x_mean = sum(times_min) / n
    y_mean = sum(temps) / n
    num = sum((times_min[i] - x_mean) * (temps[i] - y_mean) for i in range(n))
    den = sum((times_min[i] - x_mean) ** 2 for i in range(n))
    if den == 0.0:
        return 0.0
    slope_per_min = num / den
    return slope_per_min * 60.0  # convert to °C/hour


def _stuck_run_minutes(readings: list[dict]) -> float:
    """
    Return the length of the current stuck-value run at the end of the window.

    A 'stuck run' is a sequence of consecutive identical temp_c values ending
    at the last reading.
    """
    if len(readings) < 2:
        return 0.0
    last_val = readings[-1]["temp_c"]
    run_start_idx = len(readings) - 1
    for i in range(len(readings) - 2, -1, -1):
        if readings[i]["temp_c"] == last_val:
            run_start_idx = i
        else:
            break
    if run_start_idx == len(readings) - 1:
        return 0.0
    t_start = readings[run_start_idx]["timestamp"]
    t_end = readings[-1]["timestamp"]
    return (t_end - t_start).total_seconds() / 60.0


# ── Main entry point ──────────────────────────────────────────────────────────

def build_feature_vector(
    window_readings: list[dict],
    *,
    temp_range_min: float,
    temp_range_max: float,
    reefer_setpoint_c: float,
    leg_arrives_at: datetime,
    next_transfer_within_4h: bool,
    dwell_status: str,
    ambient_temp_forecast_c: float,
    container_type: str,
    prediction_timestamp: datetime,
) -> dict[str, Any]:
    """
    Compute all 18 features from a trailing window of sensor readings.

    Args:
        window_readings: List of dicts with keys 'timestamp' (datetime),
            'temp_c' (float), 'door_open' (bool | None).
            Must be sorted by timestamp ascending.
            Must have at least MIN_READINGS_IN_WINDOW entries (caller enforces).
        temp_range_min: Lower bound of allowed temperature range (°C).
        temp_range_max: Upper bound of allowed temperature range (°C).
        reefer_setpoint_c: Refrigeration setpoint (°C).
        leg_arrives_at: Scheduled arrival of the current leg (UTC datetime).
        next_transfer_within_4h: True if a leg transfer is scheduled within 4h.
        dwell_status: 'in_transit' | 'dwell' | 'transfer'
        ambient_temp_forecast_c: Forecast ambient temperature at current position.
        container_type: Asset type string (e.g. 'reefer_container', 'truck').
        prediction_timestamp: The timestamp at which the prediction is made.

    Returns:
        Dict mapping each feature name in FEATURE_NAMES to its value.
        Categorical features are plain strings; the caller converts to category
        dtype when building a DataFrame for the model.
    """
    if not window_readings:
        raise ValueError("window_readings must be non-empty")

    temps = [r["temp_c"] for r in window_readings]
    n = len(temps)

    # Timestamps as minutes-since-window-start for slope computation
    t0 = window_readings[0]["timestamp"]
    times_min = [
        (r["timestamp"] - t0).total_seconds() / 60.0
        for r in window_readings
    ]

    # Features 1–6: temperature statistics
    temp_current = temps[-1]
    temp_mean = sum(temps) / n
    temp_min = min(temps)
    temp_max = max(temps)
    temp_slope = _ols_slope(times_min, temps)
    temp_variance = sum((t - temp_mean) ** 2 for t in temps) / n

    # Features 7–8: distance to band limits
    dist_to_max = temp_range_max - temp_current
    dist_to_min = temp_current - temp_range_min

    # Features 9–10: door events
    door_events = [r for r in window_readings if r.get("door_open") is True]
    door_open_count = len(door_events)
    if door_events:
        last_door_ts = max(r["timestamp"] for r in door_events)
        minutes_since_last_door = (prediction_timestamp - last_door_ts).total_seconds() / 60.0
    else:
        minutes_since_last_door = SENTINEL_NO_DOOR_EVENT

    # Feature 15: hours remaining on leg
    if prediction_timestamp.tzinfo is None:
        prediction_timestamp = prediction_timestamp.replace(tzinfo=timezone.utc)
    if leg_arrives_at.tzinfo is None:
        leg_arrives_at = leg_arrives_at.replace(tzinfo=timezone.utc)
    hours_remaining = max(0.0, (leg_arrives_at - prediction_timestamp).total_seconds() / 3600.0)

    # Feature 18: stuck-value run
    stuck_run = _stuck_run_minutes(window_readings)

    return {
        "temp_c_current": temp_current,
        "temp_c_mean_2h": temp_mean,
        "temp_c_min_2h": temp_min,
        "temp_c_max_2h": temp_max,
        "temp_slope_c_per_h": temp_slope,
        "temp_variance_2h": temp_variance,
        "dist_to_max_c": dist_to_max,
        "dist_to_min_c": dist_to_min,
        "minutes_since_last_door_open": minutes_since_last_door,
        "door_open_count_2h": door_open_count,
        "dwell_status": dwell_status,
        "ambient_temp_forecast_c": ambient_temp_forecast_c,
        "container_type": container_type,
        "reefer_setpoint_c": reefer_setpoint_c,
        "hours_remaining_leg": hours_remaining,
        "next_transfer_within_horizon": int(next_transfer_within_4h),
        "reading_count_2h": n,
        "stuck_value_run_min": stuck_run,
    }


# ── Baseline predictor (heuristic B1) ─────────────────────────────────────────

def baseline_predict(feature_vector: dict[str, Any]) -> int:
    """
    Baseline B1: predict breach = 1 if the linear extrapolation of the
    2-hour slope crosses either range boundary within the 4-hour horizon.

    This is the strongest single-feature heuristic an operator would use
    by hand.  Model 1 must beat this on PR-AUC by ≥ 0.05 points.

    Returns 0 or 1.
    """
    current = feature_vector["temp_c_current"]
    slope = feature_vector["temp_slope_c_per_h"]
    dist_max = feature_vector["dist_to_max_c"]
    dist_min = feature_vector["dist_to_min_c"]

    projected = current + slope * HORIZON_HOURS
    # dist_to_max/min are computed relative to current temp; recompute projected dists
    temp_range_max = current + dist_max  # range_max = current + dist_to_max
    temp_range_min = current - dist_min  # range_min = current - dist_to_min

    if projected > temp_range_max:
        return 1
    if projected < temp_range_min:
        return 1
    return 0
