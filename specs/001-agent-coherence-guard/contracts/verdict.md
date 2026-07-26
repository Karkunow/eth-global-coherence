# Contract: The Verdict Object

**Shared by both interfaces.** This is the contract that makes FR-030 — identical verdicts from the dashboard and from MCP — verifiable rather than aspirational. Both call `orchestrator.run_check()`, which returns exactly this shape; neither transport reshapes it beyond serialization.

---

## Schema

```json
{
  "outcome": "PASS | VETO | NO_BASELINE | INSUFFICIENT_SAMPLES",
  "requires_acknowledgement": true,
  "confidence": 0.95,
  "note": null,

  "reading": {
    "incoherence": 0.045,
    "disagreement_sum": 1.9103,
    "std_error": 0.0212,
    "ci_low": 1.8492,
    "ci_high": 1.9714,
    "reps": 3,
    "signalling": 0.0118,
    "samples_used": 9,
    "samples_discarded": 0
  },

  "baseline": {
    "key": "a3f2c8...",
    "mean_incoherence": 0.042,
    "mean_disagreement_sum": 1.9160,
    "std_dev": 0.0187,
    "n": 12,
    "calibrated_at": "2026-07-26T09:14:22Z"
  },

  "p_value": 0.71,

  "probe": {
    "pair": ["WETH", "USDC"],
    "third": "WBTC",
    "product": 1.0007,
    "fetched_at": "2026-07-26T14:02:11Z"
  },

  "quote": {
    "amount_in": "1.0",
    "amount_out": "3891.44",
    "fee_tier": 500,
    "pool_address": "0x88e6...",
    "quoted_at": "2026-07-26T14:02:09Z"
  },

  "attestations": [
    {
      "context": "A,B",
      "rep": 0,
      "model_reported": "<model-id>",
      "response_id": "<id>",
      "provider_address": "<address>",
      "verifiability": "TeeML",
      "signature": null
    }
  ]
}
```

---

## Field rules

**`outcome`** — exactly one of four values. `NO_BASELINE` and `INSUFFICIENT_SAMPLES` are first-class outcomes, not errors: the run succeeded, the system is declining to render a judgment. A client that treats them as failures is wrong.

**`requires_acknowledgement`** — true when `outcome` is `VETO`, `NO_BASELINE`, or `INSUFFICIENT_SAMPLES`; false on `PASS`. A conforming client must obtain an explicit, deliberate user acknowledgement before proceeding when this is true — but **must not prevent proceeding**. The system advises; it does not block. (FR-025)

Blocking would assert more than the measurement supports: incoherence proves the agent contradicts itself, not that the trade is unprofitable. The warning text must say so (FR-025a).

**`confidence`** — always present, always displayed by any conforming client. (FR-022)

**`note`** — populated when the reading is significantly *better* than baseline, carrying the configuration-appears-changed notice. Null otherwise. (FR-023)

**`reading.incoherence`** — the headline figure: belief mass placeable in no possible world, as a fraction. Render as a percentage.

**`reading.std_error` / `ci_low` / `ci_high`** — **null when `reps < 3`.** A client must handle null rather than assuming a number. Null here always co-occurs with `outcome == "INSUFFICIENT_SAMPLES"`.

**`reading.signalling`** — measurement hygiene, not a verdict input. Values above ~0.05 suggest contexts are influencing each other's marginals and the reading should be distrusted. Surface it; do not gate on it.

**`baseline`** — null exactly when `outcome == "NO_BASELINE"`.

**`p_value`** — null when no comparison was performed (`NO_BASELINE`, `INSUFFICIENT_SAMPLES`).

**`attestations`** — one entry per contributing sample; length equals `reading.samples_used`. Present on every verdict that rendered a reading. (FR-008, FR-010)

`signature` is null when the provider path does not expose one (see research O1). **A null signature must not be presented as verified attestation.** Clients displaying attestation state should distinguish "model identity reported by provider" from "cryptographically signed", because conflating them overclaims.

---

## Prohibited fields

The following must **never** appear, at any nesting level:

- Any monetary figure presented as a measure of incoherence — no `dutch_book_usd`, no `guaranteed_loss`, no `$`-denominated coherence metric. (FR-013) The `quote` object's monetary fields describe the *trade*, not the measurement, and are the only permitted money in this object.
- Any field asserting correctness, profitability, safety, or manipulation-detection. (FR-031)

---

## Error responses

Distinct from the four outcomes above. These indicate the run could not complete:

```json
{ "error": "PROBE_INVALID",    "detail": "Leg product 1.043 exceeds 1% tolerance", "product": 1.043 }
{ "error": "DATA_UNAVAILABLE", "detail": "Pool data source unreachable", "source": "graph" }
{ "error": "QUOTE_UNAVAILABLE","detail": "Quoter call reverted", "source": "uniswap" }
{ "error": "INFERENCE_UNAVAILABLE", "detail": "Provider unreachable", "source": "0g" }
{ "error": "INSUFFICIENT_DATA", "detail": "7 of 9 samples unparseable", "samples_discarded": 7 }
```

**No fallback exists for any of these.** The run fails visibly and returns no verdict. There is deliberately no cached-data path to degrade into — FR-004 is enforced by the absence of that code, not by a runtime check that could be bypassed.
