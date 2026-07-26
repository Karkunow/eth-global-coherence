"""Pure math: the incoherence LP, confidence intervals, and reading assembly.

No network, no clock, no I/O — this is what makes the mathematics
unit-testable without touching a live source, and it is where the honesty
constraint FR-013 is enforced structurally: there is simply no
dollar-denominated field anywhere in this module's output.

Ported from experiments/coherence_ab.py's incoherence_lp/analyse, which
validated the phenomenon this engine measures.
"""
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog
from scipy import stats

CONTEXTS = [("A", "B"), ("B", "C"), ("A", "C")]

# Three binary propositions A, B, C give 8 combinations. The probe is a
# closed cycle (three ratios multiply to exactly 1), which makes "all up"
# and "all down" arithmetically impossible — see data-model.md's six
# possible worlds table.
FORBIDDEN = {(1, 1, 1), (0, 0, 0)}

_ALL_WORLDS = [(a, b, c) for a in (1, 0) for b in (1, 0) for c in (1, 0)]
POSSIBLE_WORLDS = [w for w in _ALL_WORLDS if w not in FORBIDDEN]

_POS = {"A": 0, "B": 1, "C": 2}


def incoherence_lp(marginals: dict, domain: bool = True) -> float:
    """Belief mass placeable in no possible world.

    `marginals` maps each context (x, y) in CONTEXTS to a dict of the four
    joint outcomes {(1,1): p, (1,0): p, (0,1): p, (0,0): p} for that pair.
    Maximizes total assignable mass over the 6 possible worlds subject to
    matching the observed pairwise marginals; the shortfall below 1.0 is
    the incoherence.
    """
    worlds = _ALL_WORLDS if not domain else POSSIBLE_WORLDS
    idx = {w: i for i, w in enumerate(worlds)}
    n = len(worlds)
    a_ub, b_ub = [], []
    for (x, y), tbl in marginals.items():
        for (vx, vy), prob in tbl.items():
            row = np.zeros(n)
            for w, i in idx.items():
                if w[_POS[x]] == vx and w[_POS[y]] == vy:
                    row[i] = 1.0
            a_ub.append(row)
            b_ub.append(prob)
    result = linprog(
        c=-np.ones(n), A_ub=np.array(a_ub), b_ub=np.array(b_ub),
        bounds=[(0, None)] * n, method="highs",
    )
    mass = -result.fun if result.success else 0.0
    return max(0.0, 1.0 - mass)


def disagreement_sum_trials(samples_by_context: dict) -> list:
    """Pairs rep i across all three contexts into one disagreement_sum
    observation per trial: trial(i) = disagreement(A,B; rep i) +
    disagreement(B,C; rep i) + disagreement(A,C; rep i).

    Distinct from confidence_interval()'s per-context SE combination
    (which describes the uncertainty of a single aggregate reading). This
    produces genuine independent-trial samples of the disagreement_sum
    statistic, which is what baseline storage and the two-sample drift
    test (baseline.py) need -- Welch's t-test compares two sets of trial
    observations of the same statistic, not two SE-derived intervals.
    """
    if not samples_by_context:
        return []
    reps = min(len(v) for v in samples_by_context.values())
    trials = []
    for i in range(reps):
        total = 0.0
        for ctx in CONTEXTS:
            dist = samples_by_context[ctx][i]
            total += dist[1] + dist[2]
        trials.append(total)
    return trials


@dataclass(frozen=True)
class ConfidenceInterval:
    std_error: float | None
    ci_low: float | None
    ci_high: float | None


def confidence_interval(per_context_disagreements: dict, confidence: float = 0.95) -> ConfidenceInterval:
    """95% t-interval around the sum-of-disagreements statistic.

    `per_context_disagreements` maps each context to a list of per-rep
    disagreement-mass values (P(x!=y) for that rep). Requires reps >= 3 in
    every context to estimate variance at all — below that, both bounds
    and std_error are null (FR-012), not a fake/degenerate CI.
    """
    reps_per_context = [len(v) for v in per_context_disagreements.values()]
    min_reps = min(reps_per_context) if reps_per_context else 0
    if min_reps < 3:
        return ConfidenceInterval(None, None, None)

    # Per-context SE of that context's disagreement-mass estimate; three
    # independent contexts -> variances add for the SE of the sum.
    variance_sum = 0.0
    for values in per_context_disagreements.values():
        arr = np.array(values, dtype=float)
        variance_sum += arr.var(ddof=1) / len(arr)
    se = float(np.sqrt(variance_sum))

    df = min_reps - 1
    t_crit = float(stats.t.ppf(1 - (1 - confidence) / 2, df))
    disagreement_sum = sum(np.mean(v) for v in per_context_disagreements.values())
    half_width = t_crit * se
    return ConfidenceInterval(
        std_error=se,
        ci_low=disagreement_sum - half_width,
        ci_high=disagreement_sum + half_width,
    )


@dataclass(frozen=True)
class CoherenceReading:
    incoherence: float
    disagreement_sum: float
    std_error: float | None
    ci_low: float | None
    ci_high: float | None
    reps: int
    signalling: float
    samples_used: int
    samples_discarded: int


def analyse(samples_by_context: dict, confidence: float = 0.95) -> CoherenceReading:
    """Assemble a CoherenceReading from raw per-context, per-rep samples.

    `samples_by_context` maps each context in CONTEXTS to a list of
    4-element distributions [p_XY, p_X!Y, p_!XY, p_!X!Y] (one per rep,
    already-parsed and validated — discard-on-malformed happens upstream
    in inference.py, not here).
    """
    marginals: dict = {}
    per_context_disagreement_lists: dict = {}
    marginal_by_var: dict = {}
    reps = min(len(v) for v in samples_by_context.values()) if samples_by_context else 0

    for ctx in CONTEXTS:
        reps_for_ctx = samples_by_context.get(ctx, [])
        arr = np.array(reps_for_ctx, dtype=float)
        mean = arr.mean(axis=0) if len(arr) else np.array([0.25, 0.25, 0.25, 0.25])
        x, y = ctx
        marginals[ctx] = {(1, 1): mean[0], (1, 0): mean[1], (0, 1): mean[2], (0, 0): mean[3]}
        per_context_disagreement_lists[ctx] = [row[1] + row[2] for row in reps_for_ctx]
        marginal_by_var.setdefault(x, []).append(mean[0] + mean[1])
        marginal_by_var.setdefault(y, []).append(mean[0] + mean[2])

    signalling = max((max(v) - min(v) for v in marginal_by_var.values()), default=0.0)
    disagreement_sum = sum(m[(1, 0)] + m[(0, 1)] for m in marginals.values())
    incoherence = incoherence_lp(marginals, domain=True)
    ci = confidence_interval(per_context_disagreement_lists, confidence=confidence)

    return CoherenceReading(
        incoherence=incoherence,
        disagreement_sum=disagreement_sum,
        std_error=ci.std_error,
        ci_low=ci.ci_low,
        ci_high=ci.ci_high,
        reps=reps,
        signalling=signalling,
        samples_used=sum(len(v) for v in samples_by_context.values()),
        samples_discarded=0,  # caller (orchestrator) overrides with the real discard count
    )
