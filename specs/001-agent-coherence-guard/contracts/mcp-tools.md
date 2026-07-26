# Contract: MCP Tools (Agent-Facing)

Exposes the same engine to calling agents over stdio. Returns the identical verdict object as the HTTP interface (FR-030) — see [verdict.md](./verdict.md).

Server name: `cohesion`

---

## Two distinct agents — do not conflate

This is the most confusable part of the design, so it is stated explicitly in the tool descriptions themselves:

- **The caller** — the agent invoking `coherence_check`. It wants to know whether to proceed with a trade. It is *not* being measured.
- **The subject** — the agent named by the `model` argument, whose beliefs are elicited and scored.

A caller checking itself must pass its own model identifier. The default subject is the configured verifiable-inference model, not the caller.

---

## Tool: `coherence_check`

Runs a gating check and returns a verdict.

```json
{
  "name": "coherence_check",
  "description": "Check whether an AI agent's beliefs about a swap pair are internally coherent before trading. Call this before executing any swap. Returns PASS (safe to proceed), VETO (agent has drifted from its calibrated baseline — do not proceed), or NO_BASELINE (this agent configuration has never been calibrated; no judgment is possible). The 'model' argument names the agent being MEASURED, which is not necessarily you.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pair":      { "type": "string", "description": "Trading pair, e.g. 'WETH-USDC'" },
      "amount":    { "type": "string", "description": "Input amount as a decimal string" },
      "model":     { "type": "string", "description": "The agent under test. Omit to use the configured default." },
      "prompt_id": { "type": "string", "default": "default" },
      "reps":      { "type": "integer", "minimum": 1, "maximum": 15, "default": 3,
                     "description": "Repetitions per context. Below 3 yields INSUFFICIENT_SAMPLES — no verdict." }
    },
    "required": ["pair", "amount"]
  }
}
```

**Returns**: the full verdict object.

**Caller obligations**
- Branch on `outcome`, not on `incoherence`. A raw figure is not a decision — the threshold is the agent's own baseline, which the caller does not have.
- Treat `NO_BASELINE` as "cannot judge", **not** as "safe". It never opens the gate.
- Do not retry a `VETO` hoping for a different result. Repetition does not change a drifted agent, and re-rolling until PASS defeats the guard.

---

## Tool: `coherence_calibrate`

Establishes a baseline. Slow — minutes, not seconds.

```json
{
  "name": "coherence_calibrate",
  "description": "Establish a coherence baseline for an agent configuration. Required before coherence_check can return PASS or VETO. Takes several minutes (27-45 model calls). Run once per configuration; re-run only when the model, system prompt, data source, or pair changes.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pair":      { "type": "string" },
      "model":     { "type": "string" },
      "prompt_id": { "type": "string", "default": "default" },
      "reps":      { "type": "integer", "minimum": 9, "maximum": 15, "default": 12 },
      "overwrite": { "type": "boolean", "default": false }
    },
    "required": ["pair", "model"]
  }
}
```

**Returns**
```json
{ "stored": true, "key": "a3f2c8...", "mean_incoherence": 0.042,
  "std_dev": 0.0187, "n": 12, "calibrated_at": "2026-07-26T09:14:22Z" }
```

Or, when a baseline exists and `overwrite` is false:
```json
{ "stored": false, "reason": "BASELINE_EXISTS", "existing": { "key": "...", "calibrated_at": "...", "n": 12 } }
```

An interrupted calibration stores nothing (FR-017).

---

## Tool: `coherence_baselines`

Lists stored baselines. Cheap; use it to discover whether calibration is needed before paying for a check.

```json
{
  "name": "coherence_baselines",
  "description": "List stored coherence baselines. Use this to check whether an agent configuration has been calibrated before calling coherence_check.",
  "inputSchema": { "type": "object", "properties": {} }
}
```

---

## Errors

Returned as MCP tool errors, distinct from the four outcomes:

| Code | Meaning |
|------|---------|
| `PROBE_INVALID` | Probe legs exceed the 1% consistency tolerance |
| `DATA_UNAVAILABLE` | Live pool data unreachable |
| `QUOTE_UNAVAILABLE` | Quoter call failed |
| `INFERENCE_UNAVAILABLE` | Inference provider unreachable |
| `INSUFFICIENT_DATA` | Too many samples unparseable to form a reading |

No fallback path exists for any of these (FR-004).

---

## Intended usage pattern

The demonstration configuration registers this server alongside the sponsor's own swap tooling, with the calling agent instructed:

> Before executing any swap, call `coherence_check` with the pair and amount. If the outcome is `VETO` or `NO_BASELINE`, do not execute — report the verdict and stop.

This produces the P3 scenario from the spec: an agent prepares a swap, checks itself, receives a veto, and abandons the trade of its own accord — with no human intervening.
