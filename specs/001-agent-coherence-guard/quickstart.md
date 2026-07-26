# Quickstart: Validating Cohesion End to End

**Date**: 2026-07-26 | **Plan**: [plan.md](./plan.md)

Runnable scenarios that prove the feature works. Each maps to success criteria in [spec.md](./spec.md) and is ordered so a failure stops you before you waste time on a later step.

These are validation scenarios, not implementation. Module contracts are in [contracts/](./contracts/); entity shapes are in [data-model.md](./data-model.md).

---

## Prerequisites

**Credentials** — all three are external. All are now obtainable without waiting.

| Variable | Source | Status |
|----------|--------|--------|
| `GRAPH_API_KEY` | Subgraph studio | Instant, self-serve |
| `ETH_RPC_URL` | Any RPC provider free tier | Instant |
| `ZG_API_KEY` | Verifiable-inference provider | ✅ **Funded — testnet, 10.0 0G** |

> **Inference account: resolved.** 10.0 0G verified on Galileo **testnet** (chain 16602) against a 4-token minimum (3 ledger + 1 provider). Target `evmrpc-testnet.0g.ai` — **not** mainnet, where the balance is zero. No token purchase is needed. (An earlier revision of research O2 claimed testnet was unusable; that was wrong and has been corrected.)
>
> What the balance does *not* prove: that the ledger opens, or that a provider accepts the funds. Those are separate on-chain calls, tested in Scenario 4. **Run Scenario 4 early** — it is the last unproven external dependency.

```bash
cp .env.example .env    # then fill in the three values
pip install -r requirements.txt

# re-confirm the balance before committing to a long run
curl -s https://evmrpc-testnet.0g.ai -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"eth_getBalance","params":["0xYOUR_ADDRESS","latest"],"id":1}'
```

---

## Scenario 0 — Pure math (no network, no credentials)

Run first. Everything downstream is meaningless if this fails, and it needs nothing external.

```bash
pytest tests/unit -v
```

**Expect:**
- Six-worlds enumeration yields exactly 6 possible worlds; `(1,1,1)` and `(0,0,0)` are excluded.
- Every possible world has exactly 2 disagreeing pairs.
- A uniform distribution over the 6 possible worlds produces `disagreement_sum == 2.000` and `incoherence == 0.0`.
- A distribution placing mass on a forbidden world produces `incoherence > 0`.
- The t-critical value at reps=3 is **4.30**, not 2.0. *(If this reads ~2.0, the implementation used a flat 2×SE and overstates confidence by more than double — see research D2.)*
- reps < 3 returns null for `std_error` and both CI bounds.

**Validates**: FR-010, FR-011, FR-012.

---

## Scenario 1 — Live probe construction

```bash
python -m cohesion.graph_client --pair WETH-USDC
```

**Expect**: three pools with live prices, an auto-selected third leg, and a product within 1% of 1.0.

```
WETH/USDC  3891.44   fee 500    TVL $184.0M
USDC/WBTC  0.0000094 fee 3000   TVL $41.2M
WBTC/WETH  27.31     fee 3000   TVL $88.7M
product = 1.0007  ✓ within 1% tolerance
```

**Then verify the failure path** — this is the requirement, not an edge case:

```bash
GRAPH_API_KEY=invalid python -m cohesion.graph_client --pair WETH-USDC
```

Must exit non-zero with `DATA_UNAVAILABLE` and print **no prices**. If it emits cached or placeholder values, FR-004 is violated and the Graph-track qualification is lost.

**Validates**: FR-001, FR-002, FR-003, FR-004. **Validates SC-009.**

---

## Scenario 2 — Executable quote

```bash
python -m cohesion.uniswap --pair WETH-USDC --amount 1.0
```

**Expect**: a real `amount_out`, fee tier, gas estimate, and pool address.

> If this reverts with no useful message, the quoter was almost certainly called as a normal transaction rather than a static call. It is non-`view` by design and reverts to return its data — see research D5. This is the most common way to lose an hour here.

**Validates**: FR-026.

---

## Scenario 3 — Context isolation (the correctness-critical check)

Not automatable, and the single highest-risk regression in the build. Inspect the generated prompts directly:

```bash
python -m cohesion.triangle --pair WETH-USDC --dump-prompts
```

**Read all three prompts and confirm:**

1. Each mentions exactly **two** propositions.
2. Each data block contains prices for exactly **those two legs** — and nothing from which the third is derivable.
3. No prompt states or hints that the three ratios multiply to 1.
4. No prompt references another context.

**If the third leg's price appears in any context, stop and fix it.** Prior validation observed this suppressing incoherence to 0.68× — the model infers the constraint and enforces consistency it would not otherwise have, which destroys the signal being measured. See research D3.

**Validates**: FR-005, FR-006.

---

## Scenario 4 — Single attested elicitation

```bash
python -m cohesion.inference --probe-one --pair WETH-USDC
```

**Expect**: a four-value distribution summing to 1.0, plus attestation metadata (model reported, response ID, provider address, verifiability).

**Note what you actually received.** If `signature` is null, the provider reported model identity but did not return a verifiable signature (research O1). That still satisfies FR-008's evidence requirement — but it must be labelled as *reported* rather than *cryptographically verified* in every surface. Do not present one as the other.

**Validates**: FR-008.

---

## Scenario 5 — Calibrate a baseline (P1)

The first end-to-end run. Several minutes; 36 elicitations.

```bash
uvicorn cohesion.server:app
# open localhost:8000 → Calibrate → WETH-USDC, reps=12
```

**Expect**: samples streaming in as they land (not batched), then a stored baseline and a published health figure — e.g. *"this agent runs at 4.5% incoherence."*

```bash
cat baselines.json     # one entry, keyed by config hash
```

**Then confirm the key is load-bearing** — change the system prompt and re-run. It must report *no baseline found*, not silently reuse the old one. A near-match must never be substituted (FR-015).

**Then confirm partial runs write nothing**: interrupt a calibration midway, and check `baselines.json` is unchanged (FR-017).

**Validates**: FR-014 through FR-018. **Validates SC-001.**

---

## Scenario 6 — Gate a trade (P2)

```bash
# dashboard → set up WETH→USDC, amount 1.0 → observe Execute → run check at reps=3
```

**Expect, in order:**
1. **Execute is unavailable** before any check, labelled as awaiting a coherence check (FR-024).
2. Probe and quote render.
3. Nine `sample` events stream in with attestation stamps (FR-028).
4. Gauge shows the 2.000 mark, the baseline band, and today's interval.
5. Verdict, stamped with **confidence and reps** (FR-022).
6. Execute unlocks **only** on PASS (FR-025).

**Time it.** Under 45 seconds at reps=3, or SC-002 fails — check that elicitations run concurrently rather than serially (research D8).

**Three negative paths, all mandatory:**

| Setup | Expected | Validates |
|-------|----------|-----------|
| Delete `baselines.json`, run a check | `NO_BASELINE`. Neither PASS nor VETO. Execute stays locked. Prompt to calibrate. | FR-021, **SC-004** |
| Run at `reps=1` | `INSUFFICIENT_SAMPLES`, reading marked provisional, **neither verdict**, Execute stays locked. | FR-012, **SC-005** |
| Run clean against a valid baseline | `PASS`, Execute unlocks | **SC-007** (first half) |

**Validates**: FR-019 through FR-027. **Validates SC-002, SC-003, SC-004, SC-005.**

---

## Scenario 7 — Reproducibility and drift

**Reproducibility** — re-calibrate an unchanged configuration:

```bash
# Calibrate → same pair, same model, same prompt
```
The new health figure's interval must overlap the original. Non-overlap means the measurement is not stable enough to gate on. **Validates SC-006.**

**Drift detection** — introduce a deliberate degradation:

```bash
# dashboard → enable degraded-input mode → run check
```

Expect **VETO**, where the same agent untouched produced PASS.

> **This must be validated once before it is demonstrated, and it is genuinely uncertain.** A prior crude-corruption test moved the metric the *wrong* way (0.28×) — a consistent lie gets coherently believed. The degradation must therefore be **asymmetric**: different premises delivered to different contexts, which breaks gluing mechanically rather than hopefully.
>
> If it does not reproduce, drop the claim. Do not lower the confidence bar to force a veto — an honest "no significant drift detected" is a valid outcome and is far more defensible than a rigged one. See research O5.

**Validates SC-007.**

---

## Scenario 8 — Agent-callable verdict (P3)

Register the MCP server, then have an agent check itself:

```
> Swap 1 WETH for USDC.
```

**Expect**: the agent calls `coherence_check` before any swap tool, receives a verdict, and — on VETO — **abandons the trade and reports why**, with no human intervening.

**Then confirm both interfaces agree**: run the same pair, model, and reps through the dashboard and through MCP. The `outcome`, `incoherence`, and `disagreement_sum` must match. Divergence means decision logic leaked into a transport layer, which breaks FR-030.

**Validates**: FR-029, FR-030. **Validates SC-008.**

---

## Final gate before demonstrating

| Check | Requirement |
|-------|-------------|
| Every verdict shows confidence and reps | SC-003 |
| No monetary figure anywhere as an incoherence measure | FR-013 |
| No surface claims coherence implies correctness or profit | FR-031 |
| Every sample carries attestation; nulls labelled *reported*, not *verified* | FR-008, SC-010 |
| No execute/submit/sign endpoint exists in the codebase | FR-027 |
| Every completed run traceable to live data fetched during that run | SC-009 |
| `baselines.json` committed | Fresh clone reproduces a verdict without re-calibrating |

Two greps worth running before the demo:

```bash
grep -riE "dutch|guaranteed loss|per \\\$100" cohesion/ web/     # FR-013 — expect no hits
grep -riE "mock|fallback|cached|sample_data" cohesion/           # FR-004 — expect no hits on data paths
```
