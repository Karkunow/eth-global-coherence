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
