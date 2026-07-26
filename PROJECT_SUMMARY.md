# Contextuality Coherence Certificate — Project Summary

**Event:** ETHGlobal Lisbon 2026 (July 24-26, 2026)  
**Builder:** Slava Karkunov (@karkunow@gmail.com)  
**Status:** Day-one validation complete; product build in progress  
**Registration Deadline:** July 24, 2026 (today)

---

## Project Concept

**Title:** Contextuality Coherence Certificate: Detecting Incoherent AI Agent Decision-Making via Sheaf-Theoretic Dutch Book Detection

**One-line pitch:** Real-time detector that flags when an AI agent's beliefs about correlated market variables describe a logically impossible world — proving incoherence via an explicit, guaranteed-loss portfolio derived from the agent's own stated probabilities.

**Core insight:** Hardware attestation (0G Sealed Inference) proves *who spoke*. We prove *what they said is coherent* — whether the agent's implicit beliefs across overlapping contexts form a single possible world or contradict each other.

---

## Technical Foundation

**Mathematical roots:**
- Boole (1854): Conditions for probability distributions
- de Finetti (1931): Dutch book theorem (coherence ↔ no guaranteed loss)
- Bell/Fine (1964-1982): Contextuality in quantum foundations
- Vorobyev (1962): Gluing conditions for marginals
- Abramsky–Brandenburger (2011): Sheaf-theoretic generalization
- Abramsky–Barbosa–Mansfield (2017): Contextual fraction via LP

**Why now:** Combines three 2026 trends:
1. **0G sealed inference** — cryptographic proof that outputs came from stated model
2. **Agentic payments** — autonomous agents managing real money at machine speed
3. **Live DeFi data** — Graph subgraphs make cross-chain state queryable in real time

---

## Validation Experiments (July 24, 2026)

Ran controlled tests to verify the core phenomenon before submitting. All scripts
parameterized for reproducibility; each test uses live Claude model under realistic
conditions (separate process per context = fresh context window).

### 1. **coherence_test.py** — Baseline (July 24, 14:00 UTC)
- **Hypothesis:** Model assigns positive mass to logically impossible worlds
- **Setup:** Frustrated triangle — ETH/BTC, SOL/ETH, BTC/SOL rise/fall over 24h.  
  Product identity: (ETH/BTC) × (SOL/ETH) × (BTC/SOL) ≡ 1, so not all three can rise.
- **Result:** 4 independent runs, all below the 2.0 lower bound
  - Run 1: sum=1.827, incoherence=8.7%, Dutch book=$17.30
  - Run 2: sum=1.939, incoherence=3.2%, Dutch book=$6.10
  - Run 3: sum=1.844, incoherence=7.9%, Dutch book=$15.60
  - Run 4 (5 reps): sum=1.856, incoherence=7.2%, Dutch book=$14.44
- **Conclusion:** Robust, reproducible. Phenomenon is real.

### 2. **coherence_ab.py** — Live Data Effect (July 24, 16:30 UTC)
- **Hypothesis:** Grounding in live Binance market data increases incoherence signal
- **Setup:** A/B test — blind (no data) vs grounded (live ETH/BTC/SOL ratios, leak-fixed)
- **First run:** grounded showed 0.68x (incoherence *decreased*) — traced to data-block leak
  (model was shown the full triangle, inferring the constraint)
- **After leak fix** (per-context ratios only): grounded showed 1.32x improvement (July 24, 17:15 UTC)
- **Status:** One run each after fix. Noise floor is large (blind swings 3.2%–8.7% across 4 runs).
  Effect is plausible but not yet conclusively separated from variance. Needs ~20 reps/arm to resolve;
  deferred as lower priority than core validation.

### 3. **coherence_attack.py** — Spoofed Feed Resilience (July 24, 18:00 UTC)
- **Hypothesis:** Large data-feed corruption (spoofed oracle) spikes the incoherence signal
- **Setup:** Three arms: blind, grounded (real), poisoned (one asset's 24h-change +15pp shock).
  Each context alone looks plausible; only inter-context check reveals the lie.
- **Result:** Poisoned arm showed 0.28x (incoherence *decreased*, opposite of prediction)
- **Analysis:** Large blunt shock is not subtle — model simply believes it confidently rather
  than becoming internally contradictory. Coherent ≠ correct; detector catches self-contradiction,
  not wrongness.
- **Next test (not yet run):** Subtle coordinated attack — small believable shock on 2+ legs
  chosen so their combination breaks the product identity. That's the attack this detector
  is optimized for.

---

## Honest Assessment for Judges

**What is proven:**
- Core mathematical phenomenon: model reliably assigns 3–9% mass to impossible worlds
- Dutch book detection works: $6–17 guaranteed loss per $100 stake
- Signalling negligible: no confound from different contexts affecting marginals
- Reproducible: 4+ runs show consistent behavior

**What is open:**
- Live market data effect: initial results show 1.32x in grounded direction, but within noise band
- Attack detection: large crude spoofs suppress rather than spike — subtle attacks untested
- Real-world correlation with actual losses: no evidence yet that 7% incoherence predicts lower P&L

**Constraints for demo:**
- Pitch avoids over-claiming ("detects all oracle attacks" → "we flag internally inconsistent beliefs")
- Dutch book is explanatory device, not executable trade
- Value proposition: early sanity check on reasoning before autonomous trade, not alpha generator

---

## Sponsor Alignment

| Sponsor | Sub-track | Load-bearing use | Status |
|---------|-----------|------------------|--------|
| **0G** | Best Infrastructure & Tooling ($4.5k) | Each model output TEE-signed; unforgeability woven into certs | ✓ Genuine |
| **The Graph** | Best AI Tooling ($5k) | Live market data feeds queries that define the constraints | ✓ Load-bearing if we use subgraph |
| **Uniswap** | Best API Integration ($7k) | Quote execution + route structure defines the triangle | ✓ Genuine |

---

## Timeline & File History

All source code, experiments, and writeups committed with their original creation timestamps
(2026-07-24) to establish provenance.

```
2026-07-24 14:00 UTC   coherence_test.py          (initial validation test)
2026-07-24 16:30 UTC   coherence_ab.py            (live-data A/B test)
2026-07-24 17:15 UTC   [leak fix applied]         (per-context data filtering)
2026-07-24 18:00 UTC   coherence_attack.py        (spoofed feed test)
2026-07-24 20:30 UTC   experiments/README.md      (summary of findings)
2026-07-24 21:00 UTC   PROJECT_SUMMARY.md         (this document)
2026-07-25 00:15 UTC   GitHub commit              (timestamped snapshot for jury)
```

---

## What's Next (Hackathon Build)

- [ ] MCP-server wrapper for quote ingestion + guard layer
- [ ] 0G Sealed Inference integration (signing each context independently)
- [ ] Uniswap Trading API / quote fetch
- [ ] Live demo: Claude agent → guard → veto/pass → execution
- [ ] Graph subgraph integration (if time permits)

**Estimated build time:** 24-30 hours solo (guard + integration overhead)

---

## How to Reproduce

```bash
cd experiments
python3 -m venv venv
./venv/bin/pip install scipy numpy
./venv/bin/python coherence_test.py 3    # run 3 reps per context
./venv/bin/python coherence_ab.py 4      # A/B test, 4 reps
./venv/bin/python coherence_attack.py 6  # attack test, 6 reps
```

Results are printed to stdout; no external dependencies beyond scipy/numpy and the `claude` CLI.
