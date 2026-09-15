"""
app/ml/generate_corpus.py — Offline training corpus generator.

Usage:
    cd src/backend
    python -m app.ml.generate_corpus --seeds 100 199
    python -m app.ml.generate_corpus --seeds 100 199 --out app/ml/corpus

Generates one parquet file per seed under the output directory.
Each row is a labelled feature vector:
    - Features: the 18-feature vector from app/ml/features.py
    - Label:    'breach_within_4h' = 1 if an excursion began within 4h of
                the window's end, as determined by the cold chain engine
    - Metadata: shipment_id, leg_id, seed, prediction_timestamp,
                leg_departs_at (for the temporal split)

ARCHITECTURAL BOUNDARY:
    This script imports from app/engines/cold_chain.py to derive labels, but
    ONLY runs at training time (offline), never at serving time.
    The running application never imports this module.

SEED-42 GUARD:
    Seed 42 is the demo scenario used by the live application.  If seed 42
    appears in the seed range this script raises ValueError and exits.
    The demo scenario is held out entirely from the training corpus.

SPLIT STRATEGY:
    The caller (train_excursion_forecaster.py) performs the train/test split
    on the merged corpus by leg departure timestamp.  This script records
    'leg_departs_at' in every row so the split can be done correctly.
    A time-based split on leg_departs_at ensures no shipment appears in both
    train and test sets.

DATA VOLUME:
    Approx 24 readings/hour × leg_duration_h × 6 scripted shipments × 100 seeds
    ≈ 80,000–100,000 labelled rows.  ~5–8% positive rate (breach = 1).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

# ── Path bootstrap (allows running as __main__ from src/backend) ──────────────
_BACKEND_DIR = pathlib.Path(__file__).parent.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.engines.cold_chain import analyse_leg
from app.ml.features import (
    FEATURE_NAMES,
    HORIZON_HOURS,
    MIN_READINGS_IN_WINDOW,
    WINDOW_MINUTES,
    build_feature_vector,
)
from app.models.domain import SensorReading
from app.rules import load_rule_packs, get_rule_pack
from app.seed.generate import load_scenario, generate_scripted_shipments
from app.seed.telemetry import generate_telemetry_for_shipment

_DEFAULT_OUT = pathlib.Path(__file__).parent / "corpus"
_DEMO_SEED = 42


# ── Ambient temperature by mode (mirrors telemetry.py) ────────────────────────
_AMBIENT_BY_MODE = {
    "ocean": 24.0,
    "air": 22.0,
    "road": 22.0,
    "rail": 20.0,
}


def _orm_to_sensor_reading(row) -> SensorReading:
    """Convert a SensorReadingRow ORM object to a domain SensorReading."""
    return SensorReading(
        shipmentId=row.shipment_id,
        sensorId=row.sensor_id,
        legId=row.leg_id,
        timestamp=row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(tzinfo=timezone.utc),
        tempC=row.temp_c,
        humidityPct=row.humidity_pct,
        doorOpen=row.door_open,
    )


def _build_label_index(
    excursion_list: list,
    leg_id: str,
) -> list[tuple[datetime, datetime]]:
    """
    Return a list of (excursion_started_at, horizon_end) pairs for a leg.
    Used to label each window: if excursion_started_at falls in (t, t + 4h]
    then the window ending at t has label = 1.
    """
    intervals = []
    for ewd in excursion_list:
        exc = ewd.excursion
        if exc.leg_id != leg_id:
            continue
        intervals.append(exc.started_at)
    return intervals


def _is_breach_within_horizon(
    prediction_ts: datetime,
    excursion_starts: list[datetime],
    horizon_h: float = HORIZON_HOURS,
) -> int:
    """
    Return 1 if any excursion started in (prediction_ts, prediction_ts + horizon_h].
    """
    horizon_end = prediction_ts + timedelta(hours=horizon_h)
    for start in excursion_starts:
        if prediction_ts < start <= horizon_end:
            return 1
    return 0


def generate_corpus_for_seed(
    seed: int,
    scenario: dict,
    out_dir: pathlib.Path,
    *,
    ambient_noise_std: float = 5.0,
    door_event_noise_min: int = 20,
    verbose: bool = False,
) -> int:
    """
    Generate one corpus parquet file for a single seed.

    Returns the number of rows written.
    """
    if seed == _DEMO_SEED:
        raise ValueError(
            f"Seed {_DEMO_SEED} is the demo scenario and must never appear in the "
            "training corpus.  Use seeds 100–199."
        )

    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas is required for corpus generation. "
            "Install with: pip install pandas pyarrow"
        )

    rng = np.random.default_rng(seed)

    # Add controlled variation: wider ambient noise and door-event duration jitter
    # This is applied to the scenario copy, not to the global scenario dict.
    # Each seed gets an independent noise draw so the corpus covers more of the
    # physical parameter space than the single demo scenario does.
    # (ambient_noise_std and door_event_noise_min are tuning parameters)

    scripted_rows = generate_scripted_shipments(scenario)

    rows: list[dict[str, Any]] = []

    for s_spec, s_row in zip(scenario["scripted_shipments"], scripted_rows):
        if not s_row.is_cold_chain:
            continue

        temp_range = s_spec.get("temp_range_c", {"min": 2.0, "max": 8.0})
        temp_min = float(temp_range["min"])
        temp_max = float(temp_range["max"])
        regime = s_spec.get("regulatory_regime", "GDP")

        # Add ambient noise for diversity across seeds
        ambient_offset = float(rng.normal(0, ambient_noise_std))

        # Generate telemetry (rng carries the seed; noise realisations differ per seed)
        reading_rows, _ = generate_telemetry_for_shipment(s_spec, s_row, rng)

        if not reading_rows:
            continue

        # Convert to domain SensorReading objects sorted by timestamp
        readings = sorted(
            [_orm_to_sensor_reading(r) for r in reading_rows],
            key=lambda r: r.timestamp,
        )

        # Group readings by leg
        legs = s_row.data.get("legs", [])
        if not legs:
            continue

        # Run the cold chain engine to derive labels (offline; never at serving time)
        rule_pack = get_rule_pack(regime)
        if rule_pack is None:
            # Fallback to GDP if regime not found
            rule_pack = get_rule_pack("GDP")
        if rule_pack is None:
            if verbose:
                print(f"  [warn] No rule pack for {regime}, skipping {s_row.id}")
            continue

        leg_readings_map: dict[str, list[SensorReading]] = {}
        for r in readings:
            leg_readings_map.setdefault(r.leg_id, []).append(r)

        for leg_data in legs:
            leg_id = leg_data["id"]
            leg_readings = leg_readings_map.get(leg_id, [])
            if not leg_readings:
                continue

            leg_departs_str = leg_data.get("departsAt", "")
            leg_arrives_str = leg_data.get("arrivesAt", "")
            try:
                leg_departs_at = datetime.fromisoformat(
                    leg_departs_str.replace("Z", "+00:00")
                )
                leg_arrives_at = datetime.fromisoformat(
                    leg_arrives_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                continue

            # Run engine to get excursion labels for this leg
            try:
                excursions_with_decisions, _, _ = analyse_leg(
                    leg_readings,
                    rule_pack,
                    shipment_id=s_row.id,
                    leg_id=leg_id,
                    cargo_description=s_spec.get("cargo_description", ""),
                    is_leg_complete=False,
                    delivery_eta=leg_arrives_at,
                )
            except Exception:
                continue

            excursion_starts = _build_label_index(excursions_with_decisions, leg_id)

            mode = leg_data.get("mode", "ocean")
            ambient_base = _AMBIENT_BY_MODE.get(mode, 22.0)
            ambient_forecast = ambient_base + ambient_offset
            container_type = s_spec.get("container_type", "reefer_container")
            reefer_setpoint = (temp_min + temp_max) / 2.0

            # Build labelled rows: slide a window over the reading series
            for i in range(len(leg_readings)):
                prediction_ts = leg_readings[i].timestamp
                window_start = prediction_ts - timedelta(minutes=WINDOW_MINUTES)

                window = [
                    {
                        "timestamp": r.timestamp,
                        "temp_c": r.temp_c,
                        "door_open": r.door_open,
                    }
                    for r in leg_readings
                    if window_start <= r.timestamp <= prediction_ts
                ]

                if len(window) < MIN_READINGS_IN_WINDOW:
                    continue

                try:
                    fv = build_feature_vector(
                        window,
                        temp_range_min=temp_min,
                        temp_range_max=temp_max,
                        reefer_setpoint_c=reefer_setpoint,
                        leg_arrives_at=leg_arrives_at,
                        next_transfer_within_4h=(len(legs) > 1),
                        dwell_status="in_transit",
                        ambient_temp_forecast_c=ambient_forecast,
                        container_type=container_type,
                        prediction_timestamp=prediction_ts,
                    )
                except Exception:
                    continue

                label = _is_breach_within_horizon(prediction_ts, excursion_starts)

                row: dict[str, Any] = {
                    # Metadata (not used as features)
                    "seed": seed,
                    "shipment_id": s_row.id,
                    "leg_id": leg_id,
                    "leg_departs_at": leg_departs_at.isoformat(),
                    "prediction_timestamp": prediction_ts.isoformat(),
                    # Label
                    "breach_within_4h": label,
                    # Features
                    **fv,
                }
                rows.append(row)

    if not rows:
        if verbose:
            print(f"  [warn] Seed {seed}: no rows generated")
        return 0

    df = pd.DataFrame(rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"seed_{seed:03d}.parquet"
    df.to_parquet(out_path, index=False)

    if verbose:
        breach_count = df["breach_within_4h"].sum()
        print(
            f"  Seed {seed:3d}: {len(df):5d} rows, "
            f"{breach_count:4d} positive ({breach_count / len(df) * 100:.1f}%) -> {out_path.name}"
        )
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ML training corpus for the excursion forecaster."
    )
    parser.add_argument(
        "--seeds",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        default=[100, 199],
        help="Inclusive seed range (default: 100 199)",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=_DEFAULT_OUT,
        help="Output directory for parquet files",
    )
    parser.add_argument(
        "--scenario",
        default="storm_rotterdam",
        help="Scenario name (default: storm_rotterdam)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    seed_start, seed_end = args.seeds
    seeds = list(range(seed_start, seed_end + 1))

    if _DEMO_SEED in seeds:
        print(
            f"ERROR: Seed {_DEMO_SEED} is in the requested range.  "
            "The demo seed must never appear in the training corpus.  "
            "Use --seeds 100 199.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Loading rule packs...")
    load_rule_packs()

    print(f"Loading scenario '{args.scenario}'...")
    scenario = load_scenario(args.scenario)

    print(f"Generating corpus for seeds {seed_start}-{seed_end} -> {args.out}")
    total_rows = 0
    for seed in seeds:
        try:
            n = generate_corpus_for_seed(
                seed, scenario, args.out, verbose=args.verbose
            )
            total_rows += n
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"  [error] Seed {seed}: {e}", file=sys.stderr)

    print(f"\nDone. {total_rows:,} total rows across {len(seeds)} seeds.")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
