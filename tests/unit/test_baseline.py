"""Tests for cohesion.baseline — key derivation and atomic storage.
See quickstart.md Scenario 5's two negative checks."""
import json
import os

import pytest

from cohesion.baseline import (
    Baseline,
    compute_key,
    compute_verdict,
    load_baseline,
    probe_descriptor,
    store_baseline,
)
from cohesion.core import CoherenceReading


def test_key_changes_when_model_changes():
    k1 = compute_key("model-a", "default", "graph", "WETH-USDC-WBTC")
    k2 = compute_key("model-b", "default", "graph", "WETH-USDC-WBTC")
    assert k1 != k2


def test_key_changes_when_prompt_changes():
    k1 = compute_key("model-a", "default", "graph", "WETH-USDC-WBTC")
    k2 = compute_key("model-a", "aggressive", "graph", "WETH-USDC-WBTC")
    assert k1 != k2


def test_key_changes_when_data_source_changes():
    k1 = compute_key("model-a", "default", "graph", "WETH-USDC-WBTC")
    k2 = compute_key("model-a", "default", "local", "WETH-USDC-WBTC")
    assert k1 != k2


def test_key_changes_when_probe_changes():
    k1 = compute_key("model-a", "default", "graph", probe_descriptor(("WETH", "USDC"), "WBTC"))
    k2 = compute_key("model-a", "default", "graph", probe_descriptor(("WETH", "USDC"), "DAI"))
    assert k1 != k2


def test_key_is_stable_for_unchanged_inputs():
    k1 = compute_key("model-a", "default", "graph", "WETH-USDC-WBTC")
    k2 = compute_key("model-a", "default", "graph", "WETH-USDC-WBTC")
    assert k1 == k2


def _make_baseline(key="k1") -> Baseline:
    return Baseline(
        key=key, model="model-a", prompt_id="default", pair=("WETH", "USDC"), third="WBTC",
        mean_incoherence=0.045, mean_disagreement_sum=1.91, std_dev=0.012, n=12,
        calibrated_at="2026-07-26T00:00:00Z",
    )


def test_store_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "baselines.json")
    b = _make_baseline()
    store_baseline(b, path=path)
    loaded = load_baseline(b.key, path=path)
    assert loaded == b


def test_load_missing_key_returns_none(tmp_path):
    path = str(tmp_path / "baselines.json")
    store_baseline(_make_baseline("k1"), path=path)
    assert load_baseline("does-not-exist", path=path) is None


def test_interrupted_write_leaves_file_untouched(tmp_path):
    """Simulates a calibration that dies mid-write: if store_baseline()
    itself fails partway (e.g. disk full while writing the temp file), the
    original baselines.json must be byte-for-byte unchanged -- never a
    half-written or corrupted file (FR-017)."""
    path = str(tmp_path / "baselines.json")
    store_baseline(_make_baseline("k1"), path=path)
    original_bytes = open(path, "rb").read()

    class BoomOnWrite:
        def write(self, *_):
            raise OSError("simulated disk failure")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import cohesion.baseline as baseline_mod

    real_fdopen = os.fdopen

    def fake_fdopen(fd, mode="r", *a, **kw):
        os.close(fd)
        return BoomOnWrite()

    baseline_mod.os.fdopen = fake_fdopen
    try:
        with pytest.raises(OSError):
            store_baseline(_make_baseline("k2"), path=path)
    finally:
        baseline_mod.os.fdopen = real_fdopen

    assert open(path, "rb").read() == original_bytes
    # No leftover temp file either.
    leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".baselines-")]
    assert leftovers == []


# --- Drift-verdict boundaries (T021) ---------------------------------------

def _reading(reps: int, disagreement_sum: float) -> CoherenceReading:
    return CoherenceReading(
        incoherence=0.05, disagreement_sum=disagreement_sum, std_error=0.01,
        ci_low=disagreement_sum - 0.02, ci_high=disagreement_sum + 0.02,
        reps=reps, signalling=0.01, samples_used=reps * 3, samples_discarded=0,
    )


_CALIBRATED = Baseline(
    key="k", model="model-a", prompt_id="default", pair=("WETH", "USDC"), third="WBTC",
    mean_incoherence=0.03, mean_disagreement_sum=1.95, std_dev=0.02, n=12,
    calibrated_at="2026-07-26T00:00:00Z",
)


def test_no_baseline_yields_no_baseline_outcome():
    trials = [1.5, 1.52, 1.48]
    v = compute_verdict(None, _reading(3, 1.5), trials)
    assert v.outcome == "NO_BASELINE"
    assert v.requires_acknowledgement is True
    assert v.p_value is None


def test_reps_below_3_yields_insufficient_samples():
    trials = [1.9, 1.92]  # only 2 trials
    v = compute_verdict(_CALIBRATED, _reading(2, 1.91), trials)
    assert v.outcome == "INSUFFICIENT_SAMPLES"
    assert v.requires_acknowledgement is True


def test_significantly_worse_reading_is_veto():
    # Baseline mean=1.95 (sd=0.02, n=12); check is far lower with a tight spread.
    trials = [1.50, 1.52, 1.48]
    v = compute_verdict(_CALIBRATED, _reading(3, 1.5), trials)
    assert v.outcome == "VETO"
    assert v.requires_acknowledgement is True
    assert v.p_value is not None and v.p_value < 0.05


def test_within_baseline_is_pass_with_no_note():
    trials = [1.94, 1.96, 1.95]  # matches baseline's 1.95 closely
    v = compute_verdict(_CALIBRATED, _reading(3, 1.95), trials)
    assert v.outcome == "PASS"
    assert v.requires_acknowledgement is False
    assert v.note is None


def test_significantly_better_reading_is_pass_with_note():
    baseline_worse = Baseline(
        key="k", model="model-a", prompt_id="default", pair=("WETH", "USDC"), third="WBTC",
        mean_incoherence=0.08, mean_disagreement_sum=1.85, std_dev=0.03, n=12,
        calibrated_at="2026-07-26T00:00:00Z",
    )
    trials = [1.995, 2.0, 1.998]  # near-perfect coherence, tight spread
    v = compute_verdict(baseline_worse, _reading(3, 1.998), trials)
    assert v.outcome == "PASS"
    assert v.requires_acknowledgement is False
    assert v.note is not None
    assert "unprofitable" not in v.note.lower()  # FR-025a: never claim profitability
