"""
app/ml — Predictive ML layer.

Architectural boundary (non-negotiable):
  - This layer MAY forecast future states, estimate durations, score sensor
    health, and cluster patterns.
  - This layer may NEVER classify excursion severity, assign a regulatory
    citation, decide a disposition, or produce any value that a Decision
    record depends on.

Severity classification stays in app/engines/cold_chain.py against the YAML
rule packs, unchanged by this layer.

Every prediction carries: predicted value, calibrated confidence, model id +
version, feature vector, and a predicted_at timestamp. Predictions are stored
in their own 'predictions' table and never written into columns the engines own.

When ML_ENABLED=false (the default when no artifact is present) every predictor
returns None and the caller falls back to its heuristic baseline. The application
is fully functional in that state.
"""
