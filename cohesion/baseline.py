"""Baseline storage, key derivation, and (added in US2) the drift verdict.

Storage is a single flat JSON file (plan.md's Storage decision) — small
enough that atomic write-temp-then-rename is all the durability this
needs, and it keeps the artifact reviewable and committable so a fresh
clone reproduces a demo verdict without recalibrating.
"""
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats as scipy_stats

BASELINES_PATH = "baselines.json"


def compute_key(model: str, prompt_id: str, data_source: str, probe_descriptor: str) -> str:
    """key = sha256(model, prompt, data_source, probe_descriptor), serialized
    unambiguously via json.dumps (a plain delimiter risks collision if any
    field contains it). Changing any one of the four inputs changes the key
    (FR-015) -- this is the re-check trigger list, not incidental hashing."""
    raw = json.dumps([model, prompt_id, data_source, probe_descriptor])
    return hashlib.sha256(raw.encode()).hexdigest()


def probe_descriptor(pair: tuple, third: str) -> str:
    return f"{pair[0]}-{pair[1]}-{third}"


@dataclass(frozen=True)
class Baseline:
    key: str
    model: str
    prompt_id: str
    pair: tuple
    third: str
    mean_incoherence: float
    mean_disagreement_sum: float
    std_dev: float
    n: int
    calibrated_at: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pair"] = list(d["pair"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Baseline":
        d = dict(d)
        d["pair"] = tuple(d["pair"])
        return cls(**d)


def _read_all(path: str = BASELINES_PATH) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def load_baseline(key: str, path: str = BASELINES_PATH) -> Baseline | None:
    all_baselines = _read_all(path)
    if key not in all_baselines:
        return None
    return Baseline.from_dict(all_baselines[key])


def list_baselines(path: str = BASELINES_PATH) -> list:
    return [Baseline.from_dict(d) for d in _read_all(path).values()]


def store_baseline(baseline: Baseline, path: str = BASELINES_PATH) -> None:
    """Atomic write-temp-then-rename: either the new file lands whole, or
    the original is untouched. A calibration run that raises before this is
    called leaves baselines.json exactly as it was (FR-017) -- there is no
    intermediate/partial state written by this function at all."""
    all_baselines = _read_all(path)
    all_baselines[baseline.key] = baseline.to_dict()

    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".baselines-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(all_baselines, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


@dataclass(frozen=True)
class Verdict:
    outcome: str  # "PASS" | "VETO" | "NO_BASELINE" | "INSUFFICIENT_SAMPLES"
    reading: dict
    baseline: dict | None
    p_value: float | None
    confidence: float
    note: str | None
    requires_acknowledgement: bool

    def to_dict(self) -> dict:
        return asdict(self)


def compute_verdict(baseline_obj, reading, trials: list, confidence: float = 0.95) -> Verdict:
    """The decision rule (FR-019 through FR-023):

        if no baseline for config_key      -> NO_BASELINE          (ack required)
        elif reps < 3                      -> INSUFFICIENT_SAMPLES (ack required)
        elif reading significantly WORSE   -> VETO                 (ack required)
        elif reading significantly BETTER  -> PASS + note          (proceed freely)
        else                                -> PASS                 (proceed freely)

    "Significantly" is a one-sided Welch's t-test at `confidence`, always
    against the stored baseline -- never a fixed threshold (FR-019).
    `trials` is core.disagreement_sum_trials() for the current reading:
    genuine per-trial samples of the disagreement_sum statistic, compared
    against the baseline's own (mean, std_dev, n) via
    scipy.stats.ttest_ind_from_stats (the summary-statistics form of
    Welch's test, since the baseline stores only summary stats, not raw
    trials -- see data-model.md's Baseline entity).

    "Worse" means further from 2.000, i.e. a LOWER disagreement_sum than
    baseline; "better" means a HIGHER one. Reading.reps as the sample-size
    check mirrors core.confidence_interval()'s own reps>=3 floor (FR-012).
    """
    reading_dict = {
        "incoherence": reading.incoherence, "disagreement_sum": reading.disagreement_sum,
        "std_error": reading.std_error, "ci_low": reading.ci_low, "ci_high": reading.ci_high,
        "reps": reading.reps, "signalling": reading.signalling,
        "samples_used": reading.samples_used, "samples_discarded": reading.samples_discarded,
    }

    if baseline_obj is None:
        return Verdict("NO_BASELINE", reading_dict, None, None, confidence, None, True)

    if reading.reps < 3 or len(trials) < 2:
        return Verdict("INSUFFICIENT_SAMPLES", reading_dict, baseline_obj.to_dict(), None,
                        confidence, None, True)

    current_mean = float(np.mean(trials))
    current_std = float(np.std(trials, ddof=1))
    current_n = len(trials)

    alternative = "less" if current_mean < baseline_obj.mean_disagreement_sum else "greater"
    _t_stat, p_value = scipy_stats.ttest_ind_from_stats(
        mean1=current_mean, std1=current_std, nobs1=current_n,
        mean2=baseline_obj.mean_disagreement_sum, std2=baseline_obj.std_dev, nobs2=baseline_obj.n,
        equal_var=False, alternative=alternative,
    )
    p_value = float(p_value)
    significant = p_value < (1 - confidence)

    if alternative == "less" and significant:
        return Verdict("VETO", reading_dict, baseline_obj.to_dict(), p_value, confidence, None, True)
    if alternative == "greater" and significant:
        note = "Reading is significantly better than baseline -- this also indicates the configuration has changed."
        return Verdict("PASS", reading_dict, baseline_obj.to_dict(), p_value, confidence, note, False)
    return Verdict("PASS", reading_dict, baseline_obj.to_dict(), p_value, confidence, None, False)
