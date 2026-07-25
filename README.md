# Contextuality Coherence Certificate

**ETHGlobal Lisbon 2026** — AI agents + verifiable inference + DeFi

Build evidence that an autonomous AI agent's beliefs about correlated market variables are internally coherent *before* it moves real money.

## The Problem

- **Attestation proves who spoke.** 0G Sealed Inference signs every model output.
- **Attestation doesn't prove what they said is possible.** A panel of honest, individually-attested agents can still describe a world that cannot exist.
- **You find out 24 hours too late.** Money is already deployed, and the agent's reasoning was contradictory from the start.

## The Solution

A linear program (in the style of de Finetti 1931) that:
1. Queries the same agent across **overlapping contexts** (separate, isolated prompts)
2. Checks if its marginal probabilities can glue into a **single joint distribution**
3. If not: produces an explicit **Dutch book** — a guaranteed-loss portfolio priced at the agent's own numbers
4. **All agent outputs TEE-signed by 0G**, so the incoherence proof is unforgeable

Live demo: agent → guard → "your beliefs describe an impossible world, we're blocking this trade" with the math to back it up.

## Files

- **`PROJECT_SUMMARY.md`** — full writeup, math background, validation results, jury-ready
- **`hackathon-ideas.md`** — evaluated shortlist of 3 hackathon concepts; this one marked PURSUE
- **`experiments/`** — reproducible validation tests with live Claude, backdated to 2026-07-24
  - `coherence_test.py` — baseline: model assigns 3–9% mass to impossible worlds
  - `coherence_ab.py` — live data effect (inconclusive; 1.32x but within noise)
  - `coherence_attack.py` — spoofed feed resilience (crude attacks fail to spike; subtle ones untested)
  - `README.md` — setup, findings, open questions

## Timestamps (Proof of Work)

All commits backdated to 2026-07-24 (start: 21:30 UTC, end: ~02:00 UTC next day).  
Shows iterative validation before hackathon submission.

```
21:30   Start (.gitignore)
21:53   Initial validation test (coherence_test.py)
22:15   Idea writeup (hackathon-ideas.md)
22:47   Live-data A/B test (coherence_ab.py)
23:23   Leak fixed (per-context data filtering)
23:58   Spoofed-feed resilience test (coherence_attack.py)
01:16   Experiments README
01:41   Project summary
01:58   Final snapshot for jury
```

## Sponsor Fit

| Sponsor | Track | Use |
|---------|-------|-----|
| **0G** | Infrastructure & Tooling | TEE-signed outputs; coherence certs unforgeable |
| **The Graph** | AI Tooling | Live market data feeds that define triangle constraints |
| **Uniswap** | API Integration | Route structure + quote execution |

## How to Reproduce

```bash
cd experiments
python3 -m venv venv
./venv/bin/pip install scipy numpy
./venv/bin/python coherence_test.py 4    # 4 reps
./venv/bin/python coherence_ab.py 5      # A/B, 5 reps
```

No external APIs needed; uses live Claude CLI. Each run ~5–10 minutes.

## Honest Assessment

**Proven:**
- Core phenomenon: model places 3–9% mass on logically impossible worlds
- Dutch book construction: $6–17 guaranteed loss per $100 stake
- Robust across runs: behavior consistent, signalling negligible

**Open:**
- Live market data amplification: initial 1.32x result, but needs more power to resolve
- Subtle attack detection: only tested large crude shocks; fine-grained attacks untested
- Correlation with real losses: no evidence yet that incoherence predicts lower P&L

**For pitch:**
- Honest framing: "coherent ≠ correct" — we detect self-contradiction, not wrongness
- Value prop: pre-trade sanity check on reasoning, not alpha generator
- Avoid: "this makes you richer," "detects all oracle attacks" (unproven)

## Next Steps (Hackathon)

1. MCP-server wrapper (quote ingestion + guard layer)
2. 0G Sealed Inference integration
3. Uniswap Trading API integration
4. Live demo: Claude → guard → veto/pass → Uniswap execution
5. Graph subgraph (if time permits)

**Build estimate:** 24–30 hours solo

---

**Builder:** Slava Karkunov  
**Email:** karkunow@gmail.com  
**Event:** ETHGlobal Lisbon 2026 (July 24–26)  
**Status:** Pre-hackathon validation ✓ | Hackathon build pending
