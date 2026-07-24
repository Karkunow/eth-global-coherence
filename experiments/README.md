# Coherence detector — validation experiments

Scripts that test the core idea (Contextuality Coherence Certificate) against a
live model before committing to the build. See `../hackathon-ideas.md` for the
full idea writeup.

## Setup

```bash
cd experiments
python3 -m venv venv
./venv/bin/pip install scipy numpy
```

Requires the `claude` CLI on PATH (used as the model under test — each call is
a fresh subprocess, i.e. a fresh context window, which is what makes the
separate-contexts elicitation valid).

## Scripts

- **`coherence_test.py [reps]`** — the original single-arm test. Triangle:
  ETH/BTC, SOL/ETH, BTC/SOL rise/fall, no market data in the prompt. Computes
  the frustrated-triangle deviation, no-signalling check, and both the strict
  contextual-fraction LP and the domain-constrained incoherence LP.

- **`coherence_ab.py [reps]`** — two arms: `blind` (no data) vs `grounded`
  (live Binance 24h stats injected, leak-fixed so each context only sees the
  two ratios relevant to it — see comments in `market_block()`). Tests
  whether live data changes incoherence.

- **`coherence_attack.py [reps] [shock_pct]`** — three arms: `blind`,
  `grounded`, `poisoned` (one asset's 24h-change figure is spoofed by
  `shock_pct` percentage points, simulating a manipulated/spoofed oracle
  feed, while each individual context still looks internally plausible).
  Tests whether the incoherence signal spikes under a data-feed attack.

## Findings so far (2026-07-25)

- **Core phenomenon is real and reproducible.** Across 6 independent blind
  runs, the model reliably places 3–9% of its belief mass on logically
  impossible worlds (Dutch book $6–17 per $100 stake). Signalling stays
  negligible (≤0.02) throughout, so the measurement is clean.
- **Live-data effect is inconclusive.** One leaked run showed grounded data
  *reducing* incoherence (0.68x) — traced to the market-data block revealing
  the third proposition's ratio, letting the model infer the constraint.
  After fixing the leak (per-context ratios only), a re-run showed the
  opposite (1.32x) — but single-run noise (blind alone swings 3.2%–8.7%
  across runs) is larger than this effect. Needs ~20+ reps/context/arm to
  resolve properly; not yet done.
- **First poisoned-feed attack test did NOT show a spike** (poisoned/grounded
  ratio 0.28x, i.e. incoherence went *down* under a spoofed +15pp shock on
  ETH's 24h change). This is the opposite of the hoped-for result and needs
  investigation before claiming "detects manipulated feeds" in the pitch —
  see live discussion for hypotheses (e.g. a large, obviously-anomalous shock
  may make the model discount that leg entirely rather than propagate
  inconsistent belief into the triangle).

## Honest framing for the pitch (validated so far)

Use: *"If anyone traded at this agent's own stated probabilities, they would
lose $X per $100 with certainty, in every possible world. Nobody is offering
that trade — the number measures how far its picture of the market is from
being a possible picture at all."*

Do NOT yet claim: that live market data increases incoherence, or that a
poisoned feed is detected — neither is established by the data so far.
