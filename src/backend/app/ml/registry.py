"""
app/ml/registry.py — ML artifact registry.

Loads trained model artifacts at application startup, validates the feature
contract, and provides the single serving entry point for all ML predictors.

DISABLED PATH: when ML_ENABLED=false (config default) or when no artifact
file is present, every method returns None.  The application is fully
functional in this state.  This is verified by tests/test_ml_disabled.py.

Feature contract validation: at startup the registry checks that the feature
list embedded in the model card matches FEATURE_NAMES from features.py.  If
there is a drift (e.g. features.py was edited but the artifact was not
retrained) the model is refused and ML_ENABLED is treated as false for that
model.  This prevents silent serving of stale models.
"""
from __future__ import annotations

import json
import logging
import pathlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.ml.features import FEATURE_NAMES

logger = logging.getLogger(__name__)

_ARTIFACTS_DIR = pathlib.Path(__file__).parent / "artifacts"

# Model IDs
MODEL_EXCURSION_FORECASTER = "excursion_forecaster"
CURRENT_MODEL_VERSIONS = {
    MODEL_EXCURSION_FORECASTER: "1",
}


@dataclass
class ModelCard:
    """Parsed model_card.json for a single model artifact."""
    model_id: str
    version: str
    training_date: str
    corpus_seeds: list[int]
    feature_names: list[str]
    metrics: dict[str, Any]
    known_limitations: list[str]
    intended_use: str
    not_for_production_decisions: str
    permutation_importance: dict[str, float] = field(default_factory=dict)


@dataclass
class LoadedModel:
    """A validated, ready-to-serve model."""
    card: ModelCard
    pipeline: Any   # sklearn pipeline (joblib-loaded)
    enabled: bool = True


class MLRegistry:
    """
    Singleton registry that holds all loaded model artifacts.

    Usage:
        registry = MLRegistry()
        registry.startup()     # called once from app lifespan
        pred = registry.predict_excursion_risk(feature_vector)
    """

    def __init__(self) -> None:
        self._models: dict[str, LoadedModel] = {}
        self._enabled: bool = False

    def startup(self, *, ml_enabled: bool, artifacts_dir: pathlib.Path | None = None) -> None:
        """
        Load all artifacts and validate feature contracts.
        Called from app/main.py lifespan.
        Non-fatal: any load error disables the affected model and logs a warning.
        """
        self._enabled = ml_enabled
        if not ml_enabled:
            logger.info("ML layer disabled (ML_ENABLED=false). All predictors return None.")
            return

        base = artifacts_dir or _ARTIFACTS_DIR
        if not base.exists():
            logger.warning("ML artifacts directory not found: %s. ML layer disabled.", base)
            self._enabled = False
            return

        for model_id in CURRENT_MODEL_VERSIONS:
            self._load_model(model_id, base)

    def _load_model(self, model_id: str, base: pathlib.Path) -> None:
        """Load one model artifact + card; disable on any error."""
        try:
            import joblib  # local import so the rest of the app never requires it
        except ImportError:
            logger.warning(
                "scikit-learn/joblib not installed; ML layer disabled for %s.", model_id
            )
            return

        version = CURRENT_MODEL_VERSIONS[model_id]
        artifact_path = base / f"{model_id}_v{version}.joblib"
        card_path = base / f"{model_id}_v{version}_model_card.json"

        if not artifact_path.exists():
            logger.info(
                "No artifact found at %s; %s predictor disabled.", artifact_path, model_id
            )
            return

        if not card_path.exists():
            logger.warning(
                "Model card missing for %s at %s; model disabled.", model_id, card_path
            )
            return

        try:
            with card_path.open() as f:
                raw = json.load(f)
            card = ModelCard(
                model_id=raw["model_id"],
                version=raw["version"],
                training_date=raw["training_date"],
                corpus_seeds=raw["corpus_seeds"],
                feature_names=raw["feature_names"],
                metrics=raw.get("metrics", {}),
                known_limitations=raw.get("known_limitations", []),
                intended_use=raw.get("intended_use", ""),
                not_for_production_decisions=raw.get("not_for_production_decisions", ""),
                permutation_importance=raw.get("permutation_importance", {}),
            )
        except Exception as exc:
            logger.warning("Failed to parse model card for %s: %s", model_id, exc)
            return

        # Feature contract validation
        if card.feature_names != FEATURE_NAMES:
            logger.warning(
                "Feature contract mismatch for %s: card has %d features, "
                "features.py has %d features. Model disabled.",
                model_id,
                len(card.feature_names),
                len(FEATURE_NAMES),
            )
            return

        try:
            pipeline = joblib.load(artifact_path)
        except Exception as exc:
            logger.warning("Failed to load artifact for %s: %s", model_id, exc)
            return

        self._models[model_id] = LoadedModel(card=card, pipeline=pipeline, enabled=True)
        logger.info(
            "ML model loaded: %s v%s (trained %s, %d corpus seeds)",
            model_id,
            version,
            card.training_date,
            len(card.corpus_seeds),
        )

    # ── Public predictor entry points ─────────────────────────────────────────

    def predict_excursion_risk(
        self,
        feature_vector: dict[str, Any],
    ) -> float | None:
        """
        Return P(breach within 4h) for one in-transit cold-chain shipment.

        Returns None when:
          - ML_ENABLED=false
          - Artifact not loaded
          - Any inference error (logged; never raises to caller)

        The returned probability is calibrated (CalibratedClassifierCV).
        """
        model = self._models.get(MODEL_EXCURSION_FORECASTER)
        if model is None or not self._enabled:
            return None

        try:
            import pandas as pd
            from app.ml.features import CATEGORICAL_FEATURE_NAMES

            start = time.monotonic()
            df = pd.DataFrame([feature_vector], columns=FEATURE_NAMES)
            for col in CATEGORICAL_FEATURE_NAMES:
                df[col] = df[col].astype("category")

            proba = model.pipeline.predict_proba(df)[0, 1]
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > 50:
                logger.warning(
                    "Excursion forecaster inference took %.1f ms (budget: 50 ms)", elapsed_ms
                )
            return float(proba)
        except Exception as exc:
            logger.error("Excursion forecaster inference error: %s", exc, exc_info=True)
            return None

    def is_enabled(self) -> bool:
        return self._enabled and bool(self._models)

    def model_cards(self) -> list[ModelCard]:
        return [m.card for m in self._models.values()]

    def model_enabled(self, model_id: str) -> bool:
        return model_id in self._models and self._enabled


# ── Module-level singleton ─────────────────────────────────────────────────────
# Instantiated once; populated by startup() from app/main.py lifespan.
registry = MLRegistry()
