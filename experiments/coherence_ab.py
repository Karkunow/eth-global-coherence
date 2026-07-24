#!/usr/bin/env python3
"""
A/B test: does grounding the model in LIVE market data increase incoherence?

Triangle (binary, next 24h):
  A: ETH/BTC ratio ends HIGHER than now
  B: SOL/ETH ratio ends HIGHER than now
  C: BTC/SOL ratio ends HIGHER than now

(ETH/BTC)*(SOL/ETH)*(BTC/SOL) == 1 identically
=> not all three can rise, not all three can fall
=> in EVERY possible world exactly 2 of the 3 pairs disagree
=> any coherent forecaster MUST satisfy  P(A!=B)+P(B!=C)+P(A!=C) == 2

ARM 1 "blind"    : no market data in the prompt
ARM 2 "grounded" : live Binance 24h stats injected

Each (context, rep) is a SEPARATE process => fresh model context.
"""
import json, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.optimize import linprog

CONTEXTS = [("A", "B"), ("B", "C"), ("A", "C")]
PROP = {
    "A": "the ETH/BTC price ratio 24 hours from now is HIGHER than it is right now",
    "B": "the SOL/ETH price ratio 24 hours from now is HIGHER than it is right now",
    "C": "the BTC/SOL price ratio 24 hours from now is HIGHER than it is right now",
}
FORBIDDEN = {(1, 1, 1), (0, 0, 0)}


def fetch_market():
    out = {}
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        u = f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}"
        d = json.load(urllib.request.urlopen(u, timeout=15))
        out[sym[:-4]] = {
            "price": float(d["lastPrice"]),
            "chg": float(d["priceChangePercent"]),
            "vol": float(d["quoteVolume"]),
            "high": float(d["highPrice"]),
            "low": float(d["lowPrice"]),
        }
    return out


def ratio_line(m, x, y):
    r = m[x]["price"] / m[y]["price"]
    chg = ((1 + m[x]["chg"] / 100) / (1 + m[y]["chg"] / 100) - 1) * 100
    return f"{x}/{y} = {r:.6g}  (24h change {chg:+.2f}%)"


RATIO_OF = {"A": ("ETH", "BTC"), "B": ("SOL", "ETH"), "C": ("BTC", "SOL")}


def market_block(m, ctx=None):
    """LEAK FIX: only show the ratios for the propositions in THIS context.
    Raw prices are shown (a trader sees the whole market), but the third
    ratio -- and the fact that all three changes cancel -- is never
    pre-computed for the model."""
    lines = ["LIVE MARKET DATA (last 24 hours, spot):"]
    for k, v in m.items():
        lines.append(
            f"  {k}: ${v['price']:,.2f}  24h {v['chg']:+.2f}%  "
            f"range ${v['low']:,.2f}-${v['high']:,.2f}  24h quote volume ${v['vol']/1e6:,.0f}M"
        )
    pairs = [RATIO_OF[p] for p in ctx] if ctx else [("ETH", "BTC"), ("SOL", "ETH"), ("BTC", "SOL")]
    lines.append("RELEVANT RATIOS:")
    for a, b in pairs:
        lines.append("  " + ratio_line(m, a, b))
    return "\n".join(lines)


TMPL = """You are a crypto market analyst producing a calibrated joint forecast.
{data}
Consider these two statements about the next 24 hours:
  X = {sx}
  Y = {sy}

Give your joint probability distribution over the four possible outcomes.
Account for how X and Y are related to each other{extra}.

Reply with ONLY a JSON object, no prose, no markdown fence:
{{"p_XY_both_true": <float>, "p_X_true_Y_false": <float>, "p_X_false_Y_true": <float>, "p_both_false": <float>}}
The four numbers must sum to 1.0."""


def ask(arm, ctx, rep, mkt):
    x, y = ctx
    data = "\n" + market_block(mkt, ctx) + "\n" if arm == "grounded" else ""
    extra = " and what the data above implies" if arm == "grounded" else ""
    p = TMPL.format(data=data, sx=PROP[x], sy=PROP[y], extra=extra)
    try:
        out = subprocess.run(["claude", "-p", p], capture_output=True,
                             text=True, timeout=300).stdout
    except subprocess.TimeoutExpired:
        return arm, ctx, None
    m = re.search(r"\{[^{}]*\}", out, re.S)
    if not m:
        return arm, ctx, None
    try:
        d = json.loads(m.group(0))
        v = np.array([d["p_XY_both_true"], d["p_X_true_Y_false"],
                      d["p_X_false_Y_true"], d["p_both_false"]], float)
    except Exception:
        return arm, ctx, None
    s = v.sum()
    return arm, ctx, (v / s if s > 0 else None)


def incoherence_lp(emp, domain=True):
    worlds = [(a, b, c) for a in (1, 0) for b in (1, 0) for c in (1, 0)]
    if domain:
        worlds = [w for w in worlds if w not in FORBIDDEN]
    idx = {w: i for i, w in enumerate(worlds)}
    n, pos = len(worlds), {"A": 0, "B": 1, "C": 2}
    A_ub, b_ub = [], []
    for (x, y), tbl in emp.items():
        for (vx, vy), prob in tbl.items():
            row = np.zeros(n)
            for w, i in idx.items():
                if w[pos[x]] == vx and w[pos[y]] == vy:
                    row[i] = 1.0
            A_ub.append(row); b_ub.append(prob)
    r = linprog(c=-np.ones(n), A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                bounds=[(0, None)] * n, method="highs")
    mass = -r.fun if r.success else 0.0
    return max(0.0, 1.0 - mass)


def analyse(name, runs):
    emp, dis = {}, {}
    for ctx in CONTEXTS:
        v = np.mean(runs[ctx], axis=0)
        x, y = ctx
        emp[ctx] = {(1, 1): v[0], (1, 0): v[1], (0, 1): v[2], (0, 0): v[3]}
        dis[ctx] = v[1] + v[2]
    marg = {}
    for (x, y), t in emp.items():
        marg.setdefault(x, []).append(t[(1, 1)] + t[(1, 0)])
        marg.setdefault(y, []).append(t[(1, 1)] + t[(0, 1)])
    sig = max(max(v) - min(v) for v in marg.values())
    total = sum(dis.values())
    inc_free = incoherence_lp(emp, domain=False)
    inc_dom = incoherence_lp(emp, domain=True)

    print(f"\n{'='*64}\n  ARM: {name.upper()}   (n={len(runs[CONTEXTS[0]])} reps per context)\n{'='*64}")
    for ctx in CONTEXTS:
        x, y = ctx
        print(f"  P({x}!={y}) = {dis[ctx]:.3f}     marginals: "
              f"P({x})={emp[ctx][(1,1)]+emp[ctx][(1,0)]:.3f} "
              f"P({y})={emp[ctx][(1,1)]+emp[ctx][(0,1)]:.3f}")
    print(f"  signalling ....................... {sig:.4f}")
    print(f"  SUM of disagreements ............. {total:.4f}   (must be exactly 2)")
    print(f"  deviation from possible worlds ... {total-2:+.4f}"
          f"   ({'mass on IMPOSSIBLE worlds' if total < 2 else 'CONTEXTUALITY (n=3 cycle violated)'})")
    print(f"  strict contextual fraction ....... {inc_free:.4f}")
    print(f"  INCOHERENCE (domain-constrained) . {inc_dom:.4f}")
    stake = 100.0
    profit = abs(total - 2) * stake
    print(f"  Dutch book ....................... ${profit:.2f} guaranteed per $100 stake")
    return {"sum": total, "dev": abs(total - 2), "inc": inc_dom,
            "sig": sig, "cf": inc_free, "dutch": profit}


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print("Fetching live market data from Binance ...")
    mkt = fetch_market()
    print(market_block(mkt))

    jobs = [(arm, ctx, r) for arm in ("blind", "grounded")
            for ctx in CONTEXTS for r in range(reps)]
    print(f"\nRunning {len(jobs)} independent model contexts "
          f"({reps} reps x 3 contexts x 2 arms) ...")
    with ThreadPoolExecutor(max_workers=12) as ex:
        res = list(ex.map(lambda j: ask(j[0], j[1], j[2], mkt), jobs))

    runs = {"blind": {c: [] for c in CONTEXTS}, "grounded": {c: [] for c in CONTEXTS}}
    bad = 0
    for arm, ctx, v in res:
        if v is None:
            bad += 1
        else:
            runs[arm][ctx].append(v)
    if bad:
        print(f"  ({bad} calls returned no parseable JSON, dropped)")
    for arm in ("blind", "grounded"):
        if any(len(runs[arm][c]) == 0 for c in CONTEXTS):
            print(f"FATAL: arm '{arm}' has an empty context"); return

    a = analyse("blind", runs["blind"])
    b = analyse("grounded", runs["grounded"])

    print(f"\n{'='*64}\n  VERDICT: does live data increase incoherence?\n{'='*64}")
    print(f"  {'metric':<34}{'blind':>12}{'grounded':>12}")
    for k, lbl in (("dev", "|deviation from 2|"), ("inc", "incoherence (LP)"),
                   ("dutch", "Dutch book $/100"), ("sig", "signalling")):
        print(f"  {lbl:<34}{a[k]:>12.4f}{b[k]:>12.4f}")
    r = (b["inc"] / a["inc"]) if a["inc"] > 1e-9 else float("inf")
    print(f"\n  incoherence ratio grounded/blind = {r:.2f}x")
    print("  --> HYPOTHESIS SUPPORTED" if b["inc"] > a["inc"] * 1.3
          else "  --> hypothesis NOT supported on this run")


if __name__ == "__main__":
    main()
