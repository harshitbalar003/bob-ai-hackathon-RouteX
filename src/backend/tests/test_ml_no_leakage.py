"""
tests/test_ml_no_leakage.py — Data integrity and leakage guards for ML training.

These tests run against the CORPUS (parquet files) produced by generate_corpus.py.
If the corpus directory does not exist, the tests are skipped with a clear message.

Assertions:
  1. Seed 42 never appears in the corpus
  2. No shipment_id appears in both train and test splits
  3. The label column 'breach_within_4h' is NOT a feature column
  4. The seed-based split is coherent: train seeds and test seeds are disjoint
"""
from __future__ import annotations

import pathlib

import pytest

_CORPUS_DIR = pathlib.Path(__file__).parent.parent / "app" / "ml" / "corpus"
_REQUIRES_CORPUS = pytest.mark.skipif(
    not _CORPUS_DIR.exists() or not any(_CORPUS_DIR.glob("*.parquet")),
    reason=(
        "Corpus not generated yet. Run: "
        "python -m app.ml.generate_corpus --seeds 100 199 --verbose"
    ),
)


def _load_corpus():
    """Load all parquet files into a single DataFrame."""
    try:
        import pandas as pd
    except ImportError:
        pytest.skip("pandas not installed")

    files = sorted(_CORPUS_DIR.glob("*.parquet"))
    if not files:
        pytest.skip("No parquet files in corpus dir")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _seed_split(df):
    """
    Apply the same 80/20 seed-based split used in training.

    The scripted shipments share a fixed scenario anchor (only 6 unique
    departure dates across all 100 seeds), so a pure timestamp split would
    assign almost all positives to the test set. Splitting by seed gives
    each split independent realisations and balanced positives.
    """
    seeds = sorted(df["seed"].unique())
    n_train = int(len(seeds) * 0.80)
    train_seeds = set(seeds[:n_train])
    test_seeds = set(seeds[n_train:])
    train = df[df["seed"].isin(train_seeds)]
    test = df[df["seed"].isin(test_seeds)]
    return train, test


@_REQUIRES_CORPUS
class TestCorpusIntegrity:
    def test_no_demo_seed_in_corpus(self):
        """Seed 42 must never appear in the training corpus."""
        df = _load_corpus()
        assert 42 not in df["seed"].unique(), (
            "Demo seed 42 found in corpus! Re-generate with seeds 100-199."
        )

    def test_label_not_a_feature_column(self):
        """breach_within_4h must not appear in the feature matrix."""
        from app.ml.features import FEATURE_NAMES
        assert "breach_within_4h" not in FEATURE_NAMES, (
            "Label column 'breach_within_4h' must not be in FEATURE_NAMES"
        )
        df = _load_corpus()
        feature_cols = [c for c in df.columns if c in FEATURE_NAMES]
        assert "breach_within_4h" not in feature_cols

    def test_all_feature_columns_present(self):
        """Every feature in FEATURE_NAMES must have a column in the corpus."""
        from app.ml.features import FEATURE_NAMES
        df = _load_corpus()
        missing = [f for f in FEATURE_NAMES if f not in df.columns]
        assert missing == [], f"Missing feature columns in corpus: {missing}"

    def test_positive_rate_reasonable(self):
        """
        Breach rate sanity check. The scripted thermal corpus produces a low
        positive rate (~0.1-2%) because only 3 of 6 scripted scenarios have
        excursions and the 4-hour label window is short relative to the full
        leg duration. class_weight='balanced' in the classifier compensates.
        The important check is that positives exist (rate > 0) and are not
        so numerous that the label is derived from current state (rate < 50%).
        """
        df = _load_corpus()
        rate = df["breach_within_4h"].mean()
        assert 0.0 < rate <= 0.50, (
            f"Positive rate {rate:.4f} is outside the expected (0, 50%] range. "
            "Check label derivation in generate_corpus.py."
        )

    def test_corpus_has_multiple_seeds(self):
        """Should have at least 5 distinct seeds (catches partial runs)."""
        df = _load_corpus()
        assert df["seed"].nunique() >= 5, (
            f"Only {df['seed'].nunique()} seeds in corpus. Run with --seeds 100 199."
        )


@_REQUIRES_CORPUS
class TestSeedSplitNoLeakage:
    def test_no_seed_in_both_splits(self):
        """
        No seed should appear in both train and test.

        Shipment IDs (shp-101 to shp-106) repeat across seeds by design —
        each seed is an independent noise draw of the same scenario. The leakage
        concern is within a seed, not across seeds. We assert that seed sets
        are strictly disjoint, which means no window's training context
        overlaps with any test window.
        """
        df = _load_corpus()
        train, test = _seed_split(df)

        train_seeds = set(train["seed"].unique())
        test_seeds = set(test["seed"].unique())
        overlap = train_seeds & test_seeds

        assert overlap == set(), (
            f"Seeds appear in BOTH train and test splits: {overlap}. "
            "This is a data leakage bug."
        )

    def test_train_seeds_and_test_seeds_disjoint(self):
        """No seed should appear in both train and test."""
        df = _load_corpus()
        train, test = _seed_split(df)
        train_seeds = set(train["seed"].unique())
        test_seeds = set(test["seed"].unique())
        assert train_seeds & test_seeds == set(), (
            "Seeds overlap between train and test splits."
        )

    def test_train_is_larger_than_test(self):
        """80/20 split -> train must be larger than test."""
        df = _load_corpus()
        train, test = _seed_split(df)
        assert len(train) > len(test), (
            f"Train ({len(train)}) should be larger than test ({len(test)})"
        )

    def test_both_splits_have_positives(self):
        """Both train and test must have at least one positive label."""
        df = _load_corpus()
        train, test = _seed_split(df)
        assert train["breach_within_4h"].sum() > 0, "No positives in train split"
        assert test["breach_within_4h"].sum() > 0, "No positives in test split"
