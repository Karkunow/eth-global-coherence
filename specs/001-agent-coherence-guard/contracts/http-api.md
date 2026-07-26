# Contract: HTTP API (Dashboard-Facing)

Serves the browser dashboard and streams run progress. All verdict payloads conform to [verdict.md](./verdict.md).

Base: `http://localhost:8000`

---

## `GET /` — Dashboard

Serves `web/index.html`. No API contract beyond returning the page.

---

## `GET /api/pools?pair=WETH-USDC`

Builds the probe and returns its live legs. Used to render the triangle before any check runs.

**200**
```json
{
  "pair": ["WETH", "USDC"],
  "third": "WBTC",
  "product": 1.0007,
  "valid": true,
  "fetched_at": "2026-07-26T14:02:11Z",
  "legs": [
    { "pool_address": "0x88e6...", "token0": "WETH", "token1": "USDC",
      "price": 3891.44, "fee_tier": 500, "tvl_usd": 184000000 }
  ]
}
```

`valid` is false when `abs(product − 1.0) > 0.01`. A false value must block any subsequent run — the probe is not currently arbitrage-tight and the constraint it encodes does not hold. (FR-003)

**503** — `DATA_UNAVAILABLE`. No cached fallback. (FR-004)

---

## `GET /api/quote?pair=WETH-USDC&amount=1.0`

Real, executable quote for the trade being gated. (FR-026)

**200** — the `quote` object from [verdict.md](./verdict.md).

**503** — `QUOTE_UNAVAILABLE`.

---

## `GET /api/check` — SSE

Runs a gating check, streaming progress. **This is the primary endpoint.**

| Param | Default | Notes |
|-------|---------|-------|
| `pair` | required | e.g. `WETH-USDC` |
| `amount` | required | Decimal string |
| `model` | required | Subject under test |
| `prompt_id` | `default` | Identifies the system prompt |
| `reps` | `3` | 1–15; below 3 forces `INSUFFICIENT_SAMPLES` (FR-007, FR-012) |

**Event sequence**

```
event: probe        data: { pair, third, legs, product, valid }
event: quote        data: { amount_in, amount_out, fee_tier, ... }
event: baseline     data: { found: true, key, mean_incoherence, n } | { found: false }
event: sample       data: { context: "A,B", rep: 0, disagreement: 0.63, attestation: {...} }
event: sample       ...                                    ← one per elicitation, as it lands
event: reading      data: { incoherence, disagreement_sum, ci_low, ci_high, signalling }
event: verdict      data: <full verdict object>
event: done         data: { elapsed_ms: 38104 }
```

`sample` events are emitted **as each elicitation returns**, not batched at the end (FR-028). At `reps=3` the client should expect 9 of them.

**Error events** terminate the stream:
```
event: error        data: { error: "PROBE_INVALID", detail: "...", product: 1.043 }
```

**Ordering guarantees**: `probe` and `quote` always precede any `sample`. `verdict` always follows `reading`. `sample` events may interleave across contexts in any order — they are concurrent by design (research D8) and carry their own `context` and `rep` labels.

**Client obligations**
- Keep the execute affordance unavailable until `verdict` arrives, then honour `gate_open` (FR-024, FR-025).
- Display `confidence` and `reps` alongside the verdict (FR-022).
- Handle null `ci_low`/`ci_high` when reps < 3.

---

## `POST /api/calibrate` — SSE

Establishes a baseline. Same streaming shape as `/api/check`.

**Body**
```json
{ "pair": "WETH-USDC", "model": "<model-id>", "prompt_id": "default",
  "reps": 12, "overwrite": false }
```

`reps` must be 9–15 (FR-016).

**Additional events**
```
event: exists       data: { key, calibrated_at, n }   ← only when a baseline already exists and overwrite=false
event: stored       data: { key, mean_incoherence, std_dev, n }
```

On `exists` with `overwrite: false`, the stream ends without writing (FR-018). Re-issue with `overwrite: true` to replace.

**A partial run writes nothing.** If the stream terminates before `stored`, no baseline exists. (FR-017)

`/api/calibrate` is **not** covered by the 45-second budget — it issues 27–45 elicitations and is expected to take minutes.

---

## `GET /api/baselines`

Lists stored baselines for display.

**200**
```json
{ "baselines": [
  { "key": "a3f2c8...", "model": "<model-id>", "prompt_id": "default",
    "pair": ["WETH","USDC"], "third": "WBTC",
    "mean_incoherence": 0.042, "std_dev": 0.0187, "n": 12,
    "calibrated_at": "2026-07-26T09:14:22Z" }
] }
```

---

## Non-endpoints

There is **no** execute, submit, sign, or broadcast endpoint, and none may be added. The gate governs a UI affordance; nothing reaches a network. (FR-027)
