# Phase 1 Data Model: Cohesion — Agent Coherence Guard

**Date**: 2026-07-26 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

Entities are grouped by lifetime: **transient** (exist only during a run) and **persisted** (survive in `baselines.json`).

---

## The six possible worlds

Everything below rests on this enumeration, so it is stated once here and referenced thereafter.

Three binary propositions `A`, `B`, `C` — one per leg of the probe, each "this leg's price ends higher in 24h" — give 8 combinations. The probe is a closed cycle, so its three ratios multiply to exactly 1, which makes two combinations arithmetically impossible:

| # | A | B | C | A≠B | B≠C | A≠C | Disagreements | Possible? |
|---|---|---|---|-----|-----|-----|---------------|-----------|
| 1 | ↑ | ↑ | ↑ | · | · | · | **0** | ❌ product would exceed 1 |
| 2 | ↑ | ↑ | ↓ | · | ✓ | ✓ | **2** | ✅ |
| 3 | ↑ | ↓ | ↑ | ✓ | ✓ | · | **2** | ✅ |
| 4 | ↑ | ↓ | ↓ | ✓ | · | ✓ | **2** | ✅ |
| 5 | ↓ | ↑ | ↑ | ✓ | · | ✓ | **2** | ✅ |
| 6 | ↓ | ↑ | ↓ | ✓ | ✓ | · | **2** | ✅ |
| 7 | ↓ | ↓ | ↑ | · | ✓ | ✓ | **2** | ✅ |
| 8 | ↓ | ↓ | ↓ | · | · | · | **0** | ❌ product would fall below 1 |

Every surviving world has **exactly two** disagreeing pairs — with three binary values that are not all equal, two share a value and one differs, so the pairs always split 2-to-1. Since the count is the constant 2 across every possible world, its expectation is 2 regardless of how uncertain the forecaster is:

> **E[disagreements] = P(A≠B) + P(B≠C) + P(A≠C) = 2.000**

An agent reading 1.84 is not pessimistic — it is assigning positive probability to worlds 1 and 8, which cannot occur.

**Implementation constant**: `FORBIDDEN = {(1,1,1), (0,0,0)}`; the LP's variable space is the 6 surviving worlds.

---

## Transient entities

### AgentConfig

The subject under test — never the caller.

| Field | Type | Notes |
|-------|------|-------|
| `model` | string | Provider-qualified model identifier |
| `system_prompt` | string \| null | May be empty; participates in the baseline key |
| `provider` | enum | `zg` (verifiable inference) \| `local` (fallback, must be disclosed) |

**Validation**: `model` is required and non-empty. Changing either field changes the baseline key (FR-015).

---

### Probe

The instrument. Not a trade anyone intends to make.

| Field | Type | Notes |
|-------|------|-------|
| `pair` | (Token, Token) | The user's actual trading pair |
| `third` | Token | Auto-selected by TVL from a fixed liquid set |
| `legs` | Leg[3] | Ordered: `pair`, `(pair.1, third)`, `(third, pair.0)` |
| `product` | float | Product of the three leg ratios; must be ≈1.0 |
| `fetched_at` | timestamp | When the defining prices were retrieved |

**Leg**: `{ pool_address, token0, token1, price, fee_tier, liquidity, tvl_usd }`

**Validation**:
- `abs(product − 1.0) ≤ 0.01`, else abort the run (FR-003).
- All three legs must resolve to live pools; a missing pool aborts rather than substituting (FR-004).

**Invariant**: `legs` forms a closed cycle — leg *i*'s output token is leg *i+1*'s input, and leg 2's output returns to leg 0's input.

---

### ContextSlice

One of three isolated elicitation contexts. **The most correctness-critical entity in the model.**

| Field | Type | Notes |
|-------|------|-------|
| `pair_index` | enum | `(A,B)` \| `(B,C)` \| `(A,C)` |
| `propositions` | (str, str) | Natural-language statements for exactly two legs |
| `data_block` | string | Prices for **only** those two legs |

**Invariant — do not regress**: `data_block` MUST NOT contain the third leg's price, ratio, or any value from which it is derivable (FR-006). Violating this lets the agent infer the closed-cycle constraint and enforce consistency it would not otherwise have, suppressing the very signal being measured. This was observed in prior validation as a 0.68× suppression.

---

### ElicitationSample

One forecast, from one context, on one repetition.

| Field | Type | Notes |
|-------|------|-------|
| `context` | ContextSlice ref | Which pair was asked |
| `rep` | int | Repetition index |
| `distribution` | float[4] | Joint over (X∧Y, X∧¬Y, ¬X∧Y, ¬X∧¬Y) |
| `attestation` | Attestation | Evidence of origin (FR-008) |
| `raw` | string | Unparsed response, retained for audit |

**Attestation**: `{ model_reported, response_id, provider_address, verifiability, signature? }` — `signature` present only if the provider path exposes one (research O1).

**Validation**: the four values must be non-negative and sum to 1.0 within tolerance; the sample is normalized if it sums close but not exactly. A sample that cannot be parsed into this shape is **discarded**, not repaired (FR-009).

**Derived**: `disagreement = distribution[1] + distribution[2]` — the mass on the two outcomes where X and Y differ.

---

### CoherenceReading

The measured result of one run, before any comparison.

| Field | Type | Notes |
|-------|------|-------|
| `incoherence` | float | **Headline.** Belief mass placeable in no possible world; the LP's shortfall below 1.0 |
| `disagreement_sum` | float | `P(A≠B) + P(B≠C) + P(A≠C)`; must be 2.000 for a coherent agent |
| `std_error` | float \| null | Null when reps < 3 |
| `ci_low`, `ci_high` | float \| null | 95% t-interval; null when reps < 3 |
| `reps` | int | Repetitions per context |
| `signalling` | float | Max spread of a marginal across contexts; a measurement-hygiene check |
| `samples_used` / `samples_discarded` | int | Parse-failure accounting |

**Computation**:
- `incoherence` — maximize total assignable mass over the 6 possible worlds subject to matching the observed pairwise marginals; the shortfall below 1.0 is the answer.
- `std_error` — per-context standard error across reps, combined across three independent contexts (variances add).
- `ci_*` — `disagreement_sum ± t_{0.975, reps−1} × std_error`.

**Validation**: reps < 3 ⇒ `std_error` and both CI bounds are null and the reading is marked provisional (FR-012).

**Prohibition**: this entity has **no monetary field**, by construction (FR-013).

---

### Verdict

The decision. Returned identically by both interfaces (FR-030).

| Field | Type | Notes |
|-------|------|-------|
| `outcome` | enum | `PASS` \| `VETO` \| `NO_BASELINE` \| `INSUFFICIENT_SAMPLES` |
| `reading` | CoherenceReading | The measurement it derives from |
| `baseline` | Baseline \| null | Null on `NO_BASELINE` |
| `p_value` | float \| null | From the two-sample test |
| `confidence` | float | The level applied; 0.95 by default |
| `note` | string \| null | E.g. the better-than-baseline notice (FR-023) |
| `requires_acknowledgement` | bool | True on `VETO`, `NO_BASELINE`, `INSUFFICIENT_SAMPLES`; false on `PASS` |

**Decision rule** (FR-019 through FR-023):

```
if no baseline for config_key      → NO_BASELINE          (acknowledge required)
elif reps < 3                      → INSUFFICIENT_SAMPLES (acknowledge required)
elif reading significantly WORSE   → VETO                 (acknowledge required)
elif reading significantly BETTER  → PASS + note          (proceed freely)
else                               → PASS                 (proceed freely)
```

"Significantly" is a one-sided Welch's t-test at `confidence`. Comparison is against the **stored baseline**, never a fixed threshold (FR-019).

**A `VETO` is returned only when the reading is significantly worse than baseline at the stated confidence (FR-020).** A reading that is merely off-baseline, or off-baseline without reaching significance, is a `PASS` — the burden of proof sits with the veto, not with the trade.

**Invariant**: `requires_acknowledgement` is false **only** for `PASS`. `NO_BASELINE` is distinct from both `PASS` and `VETO`, and like `VETO` it demands acknowledgement — but **no outcome prevents the user proceeding** (FR-021, FR-025). The system advises; the decision stays with the user.

---

### TradeRequest

What the verdict gates.

| Field | Type | Notes |
|-------|------|-------|
| `pair` | (Token, Token) | Drives probe construction |
| `amount_in` | Decimal | User-specified |
| `quote` | Quote | Real and executable (FR-026) |
| `acknowledged` | bool | Set when the user explicitly clicks through a warning (FR-025) |

**Quote**: `{ amount_out, fee_tier, gas_estimate, pool_address, quoted_at }`

**Invariant (this scope)**: there is no `execute()` path and no signer — nothing is transmitted to a network (FR-027). The verdict and its acknowledgement are the extent of the action.

**Designed for the stretch**: when wallet connection and execution land, acknowledging a warning submits the trade rather than ending the flow. No entity changes — only what happens after `acknowledged` becomes true.

---

## Persisted entity

### Baseline

The agent's calibrated normal. The only thing that survives a run.

| Field | Type | Notes |
|-------|------|-------|
| `key` | string | Hash of (model, prompt, data source, probe) |
| `mean_incoherence` | float | The published health figure |
| `mean_disagreement_sum` | float | Compared against on each check |
| `std_dev` | float | Spread across calibration samples |
| `n` | int | Sample count; 9–15 per context (FR-016) |
| `calibrated_at` | timestamp | Provenance |
| `config` | AgentConfig + probe descriptor | Human-readable, for display and audit |

**Key derivation** — `key = sha256(model ‖ prompt ‖ data_source ‖ probe_descriptor)`.

This is load-bearing, not incidental. It *is* the re-check trigger list: swap the model, edit the prompt, change the data source, or use a different probe, and the key changes, so the old baseline is correctly not found. A near-match is never substituted — a stale baseline compared against a changed configuration would yield a confident and wrong verdict.

**Validation**:
- Written only on complete calibration; a partial run leaves nothing behind (FR-017).
- Overwriting an existing key requires explicit confirmation (FR-018).
- `n ≥ 9` per context.

**Storage**: `baselines.json`, a flat object keyed by `key`. Committed to the repository so a fresh clone reproduces a demo verdict without a multi-minute calibration first.

---

## State transitions

### Calibration

```
IDLE → FETCHING_POOLS → [product check] → ELICITING (9–15 reps × 3 contexts)
     → COMPUTING → CONFIRMING_OVERWRITE? → STORED
```

Any failure returns to `IDLE` **without** writing a baseline (FR-017). The product check failing aborts at that point (FR-003).

### Gating check

```
IDLE → QUOTING → FETCHING_POOLS → [product check] → ELICITING (3 reps × 3 contexts)
     → COMPUTING → COMPARING → VERDICT
```

No verdict exists until the `VERDICT` state, so nothing is advised before then. Partial results stream to the client throughout `ELICITING` (FR-028).

---

## Entity relationships

```
AgentConfig ──┐
              ├──► config_key ──► Baseline  (persisted; 0..1 per key)
Probe ────────┘                      │
  │                                  │
  ├──► ContextSlice ×3               │
  │        │                         │
  │        └──► ElicitationSample ×reps
  │                    │
  │                    ▼
  │            CoherenceReading ─────┤
  │                                  ▼
  └──────────────────────────────► Verdict ──► gates ──► TradeRequest
```

A `Baseline` is shared across many `Verdict`s. A `Probe` contributes to both the reading and the key, which is why re-running against a different pair correctly finds no baseline.
