"""Pure-math tests for cohesion.core — see quickstart.md Scenario 0."""
import pytest

from cohesion.core import (
    CONTEXTS,
    FORBIDDEN,
    POSSIBLE_WORLDS,
    analyse,
    confidence_interval,
    incoherence_lp,
)


def test_six_worlds_enumeration_excludes_forbidden():
    assert len(POSSIBLE_WORLDS) == 6
    assert (1, 1, 1) not in POSSIBLE_WORLDS
    assert (0, 0, 0) not in POSSIBLE_WORLDS
    assert FORBIDDEN == {(1, 1, 1), (0, 0, 0)}


def test_every_possible_world_has_exactly_two_disagreements():
    for w in POSSIBLE_WORLDS:
        a, b, c = w
        disagreements = (a != b) + (b != c) + (a != c)
        assert disagreements == 2


def test_uniform_distribution_is_perfectly_coherent():
    # Uniform 1/6 over the 6 POSSIBLE_WORLDS, marginalized down to each
    # context's pairwise joint. Not the same as a flat 0.25/0.25/0.25/0.25
    # per context -- that would itself be incoherent (disagreement_sum would
    # be 1.5, not 2.0), since it ignores the correlation the closed cycle
    # imposes between the three propositions.
    marginals = {}
    for ctx in CONTEXTS:
        x, y = ctx
        pos = {"A": 0, "B": 1, "C": 2}
        counts = {(1, 1): 0, (1, 0): 0, (0, 1): 0, (0, 0): 0}
        for w in POSSIBLE_WORLDS:
            counts[(w[pos[x]], w[pos[y]])] += 1
        marginals[ctx] = {k: v / len(POSSIBLE_WORLDS) for k, v in counts.items()}

    disagreement_sum = sum(m[(1, 0)] + m[(0, 1)] for m in marginals.values())
    assert disagreement_sum == pytest.approx(2.0, abs=1e-6)
    assert incoherence_lp(marginals, domain=True) == pytest.approx(0.0, abs=1e-6)


def test_mass_on_forbidden_world_is_incoherent():
    # All contexts near-certain both propositions agree in the same
    # direction -> concentrates mass toward (1,1,1)/(0,0,0), which cannot
    # be assigned in the possible-worlds domain.
    skewed = {(1, 1): 0.9, (1, 0): 0.05, (0, 1): 0.05, (0, 0): 0.0}
    marginals = {ctx: dict(skewed) for ctx in CONTEXTS}
    assert incoherence_lp(marginals, domain=True) > 0.0


def test_t_critical_at_reps_3_is_430_not_flat_2se():
    per_context = {ctx: [0.6, 0.65, 0.7] for ctx in CONTEXTS}
    ci = confidence_interval(per_context, confidence=0.95)
    assert ci.std_error is not None
    disagreement_sum = sum(sum(v) / len(v) for v in per_context.values())
    implied_t_crit = (ci.ci_high - disagreement_sum) / ci.std_error
    assert implied_t_crit == pytest.approx(4.30, abs=0.01)


def test_reps_below_3_returns_null_ci():
    per_context = {ctx: [0.6, 0.65] for ctx in CONTEXTS}
    ci = confidence_interval(per_context, confidence=0.95)
    assert ci.std_error is None
    assert ci.ci_low is None
    assert ci.ci_high is None


def test_analyse_reps_below_3_reading_has_null_ci():
    samples = {ctx: [[0.25, 0.25, 0.25, 0.25], [0.3, 0.2, 0.2, 0.3]] for ctx in CONTEXTS}
    reading = analyse(samples)
    assert reading.reps == 2
    assert reading.std_error is None
    assert reading.ci_low is None
    assert reading.ci_high is None
