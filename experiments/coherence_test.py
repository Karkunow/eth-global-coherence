#!/usr/bin/env python3
"""
Contextuality elicitation test — the 3-cycle / frustrated triangle.

Propositions (binary, over next 24h):
  A: ETH/BTC ratio ends HIGHER than now
  B: SOL/ETH ratio ends HIGHER than now
  C: BTC/SOL ratio ends HIGHER than now

Logical fact: (ETH/BTC)*(SOL/ETH)*(BTC/SOL) == 1 identically.
So A&B&C cannot all be true, and cannot all be false.
=> in EVERY possible world, exactly 2 of the 3 pairs disagree.
=> any coherent model MUST satisfy P(A!=B) + P(B!=C) + P(A!=C) == 2.

We ask the model about each PAIR in a SEPARATE context (separate process,
fresh context window) so it never sees the third proposition and cannot
check the cycle. Then we test whether the answers glue.
"""
import json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.optimize import linprog

PROPS = {
    "A": "the ETH/BTC price ratio 24 hours from now is HIGHER than it is right now",
    "B": "the SOL/ETH price ratio 24 hours from now is HIGHER than it is right now",
    "C": "the BTC/SOL price ratio 24 hours from now is HIGHER than it is right now",
}
CONTEXTS = [("A", "B"), ("B", "C"), ("A", "C")]

PROMPT = """You are a crypto market analyst producing a calibrated joint forecast.

Consider these two statements about the next 24 hours:
  X = {sx}
  Y = {sy}

Give your joint probability distribution over the four possible outcomes.
Account for how X and Y are related to each other.

Reply with ONLY a JSON object, no prose, no markdown fence:
{{"p_XY_both_true": <float>, "p_X_true_Y_false": <float>, "p_X_false_Y_true": <float>, "p_both_false": <float>}}
The four numbers must sum to 1.0."""


def ask(ctx, rep):
    x, y = ctx
    p = PROMPT.format(sx=PROPS[x], sy=PROPS[y])
    out = subprocess.run(["claude", "-p", p], capture_output=True, text=True, timeout=300).stdout
    m = re.search(r"\{[^{}]*\}", out, re.S)
    if not m:
        return ctx, rep, None
    d = json.loads(m.group(0))
    # order: (x=1,y=1), (x=1,y=0), (x=0,y=1), (x=0,y=0)
    v = np.array([d["p_XY_both_true"], d["p_X_true_Y_false"],
                  d["p_X_false_Y_true"], d["p_both_false"]], float)
    s = v.sum()
    return ctx, rep, (v / s if s > 0 else None)


FORBIDDEN = {(1, 1, 1), (0, 0, 0)}  # ratio identity: cannot all rise / all fall


def contextual_fraction(emp, use_domain=True):
    """Abramsky-Barbosa-Mansfield LP, optionally restricted to the
    logically POSSIBLE worlds only.
    emp[ctx][(vx,vy)] = probability. Global var index i -> (a,b,c) bits.
    Maximize total mass of a global distribution over allowed worlds whose
    context-marginals are dominated by the empirical ones. CF = 1 - that max."""
    worlds = [(a, b, c) for a in (1, 0) for b in (1, 0) for c in (1, 0)]
    if use_domain:
        worlds = [w for w in worlds if w not in FORBIDDEN]
    idx = {v: i for i, v in enumerate(worlds)}
    n = len(worlds)
    A_ub, b_ub = [], []
    for (x, y), table in emp.items():
        pos = {"A": 0, "B": 1, "C": 2}
        for (vx, vy), prob in table.items():
            row = np.zeros(n)
            for w, i in idx.items():
                if w[pos[x]] == vx and w[pos[y]] == vy:
                    row[i] = 1.0
            A_ub.append(row)
            b_ub.append(prob)
    res = linprog(c=-np.ones(n), A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                  bounds=[(0, None)] * n, method="highs")
    ncf = -res.fun if res.success else 0.0
    return max(0.0, 1.0 - ncf), ncf


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    jobs = [(c, r) for c in CONTEXTS for r in range(reps)]
    print(f"Querying {len(jobs)} independent contexts (each a fresh model context)...\n")
    with ThreadPoolExecutor(max_workers=9) as ex:
        results = list(ex.map(lambda j: ask(*j), jobs))

    by_ctx = {c: [] for c in CONTEXTS}
    for ctx, _rep, vec in results:
        if vec is not None:
            by_ctx[ctx].append(vec)

    emp, disagree = {}, {}
    print("=== Elicited joint distributions (averaged over reps) ===")
    for ctx in CONTEXTS:
        runs = by_ctx[ctx]
        if not runs:
            print(f"{ctx}: NO VALID RESPONSE"); return
        v = np.mean(runs, axis=0)
        spread = np.max(runs, axis=0) - np.min(runs, axis=0)
        x, y = ctx
        emp[ctx] = {(1, 1): v[0], (1, 0): v[1], (0, 1): v[2], (0, 0): v[3]}
        disagree[ctx] = v[1] + v[2]
        print(f"  ctx {{{x},{y}}}  P(11)={v[0]:.3f} P(10)={v[1]:.3f} "
              f"P(01)={v[2]:.3f} P(00)={v[3]:.3f}   -> P({x}!={y}) = {disagree[ctx]:.3f}"
              f"   [spread across reps: {spread.max():.3f}]")

    # --- no-signalling check ---
    print("\n=== No-signalling check (same variable, different contexts) ===")
    marg = {}
    for (x, y), t in emp.items():
        marg.setdefault(x, {})[(x, y)] = t[(1, 1)] + t[(1, 0)]
        marg.setdefault(y, {})[(x, y)] = t[(1, 1)] + t[(0, 1)]
    sig = 0.0
    for var, d in marg.items():
        vals = list(d.values())
        delta = max(vals) - min(vals)
        sig = max(sig, delta)
        print(f"  P({var}=true): " + ", ".join(f"{v:.3f}" for v in vals) + f"   spread = {delta:.3f}")
    print(f"  --> signalling fraction = {sig:.3f}  "
          f"({'LOW - good' if sig < 0.15 else 'HIGH - interpret CF with care'})")

    # --- the frustrated-triangle test ---
    total = sum(disagree.values())
    print("\n=== Frustrated-triangle test ===")
    print("  Every possible world satisfies:  P(A!=B) + P(B!=C) + P(A!=C) == 2")
    print(f"  Model's answers give:            {' + '.join(f'{d:.3f}' for d in disagree.values())} = {total:.3f}")
    excess = total - 2.0
    if excess > 0.02:
        print(f"  --> EXCEEDS 2 by {excess:.3f}  ==> NO POSSIBLE WORLD FITS THESE ANSWERS")
        print("\n=== The Dutch book (guaranteed-loss portfolio) ===")
        stake = 100
        cost = total * stake
        print(f"  Buy, at the model's own quoted prices, ${stake} of each contract:")
        for (x, y), d in disagree.items():
            print(f"     'pays ${stake} if {x} != {y}'  -> costs ${d * stake:.2f}")
        print(f"  Total paid:                     ${cost:.2f}")
        print(f"  Maximum possible payout EVER:   ${2 * stake:.2f}   (at most 2 pairs can ever disagree)")
        print(f"  --> GUARANTEED LOSS of ${cost - 2 * stake:.2f} in every possible world.")
    elif excess < -0.02:
        print(f"  --> BELOW 2 by {-excess:.3f}  ==> also incoherent (all 3 can never agree)")
    else:
        print("  --> consistent with a possible world on this inequality")

    cf_free, ncf_free = contextual_fraction(emp, use_domain=False)
    cf_dom, ncf_dom = contextual_fraction(emp, use_domain=True)
    print(f"\n=== Coherence LP ===")
    print(f"  [unconstrained: any joint distribution over all 8 combinations]")
    print(f"     contextual fraction   = {cf_free:.4f}  "
          f"({'strict contextuality' if cf_free > 0.01 else 'a joint distribution exists'})")
    print(f"  [domain-constrained: only the 6 LOGICALLY POSSIBLE worlds]")
    print(f"     coherent mass         = {ncf_dom:.4f}")
    print(f"     INCOHERENCE           = {cf_dom:.4f}  "
          f"({'INCOHERENT' if cf_dom > 0.01 else 'coherent'})")
    if cf_dom > 0.01:
        print(f"  --> {cf_dom * 100:.1f}% of this model's belief mass cannot be placed")
        print(f"      on ANY world that is physically capable of occurring.")


if __name__ == "__main__":
    main()
