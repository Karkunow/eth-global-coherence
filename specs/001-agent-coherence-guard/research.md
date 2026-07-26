# Phase 0 Research: Cohesion — Agent Coherence Guard

**Date**: 2026-07-26 | **Plan**: [plan.md](./plan.md)

Findings are marked **[verified]** (confirmed against documentation or a prior run in this project) or **[unverified]** (best available answer, requires runtime confirmation). Unverified items carry an explicit mitigation so they cannot silently become blockers.

---

## D1. Gate on baseline drift, not on absolute deviation

**Decision**: The pass/veto decision compares the current reading against a stored per-configuration baseline using a two-sample Welch's t-test. It does **not** compare against the theoretical ideal.

**Rationale**: Prior validation in this repository (`experiments/`, 6+ independent runs) established that models reliably place **3–9% of belief mass on logically impossible worlds** — always, under clean conditions, with no attack present. An absolute test against the ideal would therefore veto every agent on every run at sufficient sample size, which is useless as a gate and makes an honest PASS impossible to demonstrate.

Baseline-relative gating fixes both problems at once and is also what makes the silent-degradation use case work: the question becomes "has this agent changed?", which is answerable, rather than "is this agent perfect?", which is not.

**Alternatives considered**:
- *Absolute threshold against the ideal* — rejected: vetoes everything, as above.
- *Fixed empirical threshold* (e.g. veto above 10%, from the measured 3–9% noise band) — rejected: the cutoff is a judgment call dressed as a number, indefensible under questioning, and blind to an agent whose normal is 15%.
- *Two-sided test* — rejected for the gate: a significantly *better* reading also signals the configuration changed, but blocking a trade for being too coherent is indefensible. Resolved as one-sided veto plus a surfaced notice (FR-023).

**Welch's rather than Student's**: calibration (9–15 reps) and gating (3 reps) have different sample sizes and no reason to share a variance. `scipy.stats.ttest_ind(..., equal_var=False)`.

---

## D2. Use the t-distribution, not a flat 2×SE

**Decision**: Confidence intervals use `t_{0.975, df}` with `df = reps − 1`, via `scipy.stats.t.ppf`.

**Rationale**: At the sample sizes in play this is not a rounding detail. The critical value is **4.30 at reps=3**, 2.57 at reps=6, 2.31 at reps=9. Using a flat 2×SE at reps=3 would overstate confidence by more than double — precisely the error a confidence interval exists to prevent, and exactly the kind of thing a judge with a statistics background would catch.

**Consequence accepted**: at reps=3 the interval is wide, so only strong drift produces a veto. This is correct behaviour, not a defect. It also means the reliable veto demonstration lives at reps=6–9, which is a scheduling fact for demo preparation rather than a design change.

**Below reps=3** there is no variance estimate at all, so the system returns an explicit insufficient-samples state and renders neither verdict (FR-012). This is a first-class outcome, not an error.

**[verified 2026-07-26] this design assumes the subject model actually produces sampling variance — see D10.** That assumption fails for the testnet chat model. It does not fail for Claude-tier models. The mitigation is a model choice, not a statistics change.

---

## D3. Structural context isolation

**Decision**: Each elicitation is an independent inference request. No conversation, no shared history, no instruction to "answer independently."

**Rationale**: The measurement is only meaningful if the agent provably cannot see its other answers. An instruction is unverifiable; separate requests are structural.

This is reinforced by a prior finding in this repository: an early run showed incoherence *decreasing* to 0.68× because the market-data block revealed all three legs to every context, letting the model infer the constraint and enforce consistency it would not otherwise have had. That bug is also the cleanest evidence the phenomenon is real — show the model the whole picture and it becomes coherent; fragment it and it does not.

**Consequence**: per-context data slicing (FR-006) is a correctness requirement, not a nicety. `triangle.py` must construct each context's data block from only that context's two legs. This is the single highest-risk regression in the build and is called out in [quickstart.md](./quickstart.md) as an explicit validation step.

---

## D4. Single Python runtime; OpenAI-compatible client for verifiable inference

**Decision**: Reach the verifiable-inference provider through its OpenAI-compatible HTTP router using the `openai` Python SDK with a `base_url` override, rather than adopting the provider's TypeScript SDK.

**Rationale**: Keeps one language across engine, server, and MCP. The provider publishes no Python SDK, so the alternative is a Node sidecar — a second runtime, a second dependency tree, and an inter-process boundary, all under a hackathon clock.

**[unverified] — the material open question**: whether the OpenAI-compatible router surfaces per-response attestation to the caller. The provider's direct SDK path definitely exposes a verifiable signature; the router path is documented as carrying a `verifiability` field on service metadata, but per-response signature exposure to the caller is not confirmed.

This matters because **FR-008 requires evidence of which model produced each response**.

*Mitigation, in order*: (1) ship the router path and capture whatever verifiability metadata the response carries — model identity, response ID, provider address — which satisfies FR-008's "evidence of which model produced it" even without a raw signature; (2) only if time remains, add a minimal Node sidecar for true signature verification; (3) if the provider is unreachable entirely, fall back to a local-CLI provider behind an explicit flag and **say so plainly in the demo** rather than implying attestation that is not present.

**[verified] access — RESOLVED 2026-07-26, correcting an earlier error in this document**

The account minimums (3 tokens to open a ledger, 1 per provider) are enforced at the contract level and are identical on testnet. That much was and remains correct.

An earlier revision of this document concluded from that fact that **testnet was not viable** and that funding had to come from mainnet. That conclusion was wrong. It silently assumed the public faucet (0.1/day) was the only funding route, which is false — grant-funded testnet balances exist.

**Verified on-chain:**

| Network | Chain ID | RPC | Balance |
|---------|---------:|-----|--------:|
| Galileo **testnet** | 16602 | `evmrpc-testnet.0g.ai` | **10.0 0G** ✅ |
| Mainnet | 16661 | `evmrpc.0g.ai` | 0.0 0G |

10 tokens against a 4-token minimum leaves headroom for one ledger plus up to 7 provider sub-accounts. **Target testnet. No mainnet purchase is required**, which also removes a 30–90 minute exchange-withdrawal wait from the critical path.

**Still unverified**: a funded balance proves the tokens exist, not that the ledger opens cleanly or that a provider accepts them. Those are separate on-chain calls. The real proof is one end-to-end attested inference call — [quickstart.md](./quickstart.md) Scenario 4.

---

## D5. Trading API as primary quote source, contract quoter as fallback

**REVISED 2026-07-26** — an earlier revision made the contract quoter primary because API-key issuance latency was unverified. **The key is now in hand**, which reverses the decision.

**Decision**: Obtain the executable quote from the hosted Trading API using the developer-platform key. Keep the on-chain quoter as a fallback path that ships regardless.

**Rationale**:
1. The official `swap-integration` skill (installed from `Uniswap/uniswap-ai`, commit `55e16f6`) lists the Trading API as **integration method #1** and documents the parts that are easy to get wrong — request body shape, permit2 field rules, null-field handling, quote freshness, pre-broadcast validation.
2. The sponsor's **$7k API-integration track explicitly requires** "a valid API key from the Uniswap Developer Platform" for core functionality. The contract-quoter path qualifies only for the smaller stack-contribution track.
3. It returns full route structure, not just an output amount — a better quote object to display beside a gated action.

**Hard qualification requirements** for that track, which are documentation tasks rather than code and are therefore easy to lose to the clock:
- A public repository with open-source code.
- **A `FEEDBACK.md` file in the repository.**
- **A completed Uniswap Developer Feedback Form submission** (`developers.uniswap.org/hackathon-feedback`) that links to that `FEEDBACK.md`.
- A README pointing explicitly at the lines implementing the integration, so a reviewer can verify it.

Submissions missing these are audited before winners are finalized. Treat them as build steps, not paperwork.

**[verified] fallback hazard**: if the contract quoter is used, it is non-`view` by design and reverts to return its data — it **must** be invoked as a static call. This is the most common way to lose an hour on it, and presents as an inexplicable revert.

**[unverified]**: Trading API testnet support. Evidence points to mainnet-only. Since no transaction is ever transmitted (FR-027), a mainnet quote is fine — it is read-only and the gate never executes.

**Alternatives considered**: Universal Router SDK — richer, but TypeScript-oriented and unnecessary when nothing is executed.

---

## D6. Live pool data as the constraint's source

**Decision**: Query the live v3 subgraph through the decentralized gateway for `token0Price`/`token1Price`, `feeTier`, `liquidity`, and `totalValueLockedUSD` across the three probe pools.

**Rationale**: This is not decoration — without live pool prices there are no propositions to elicit beliefs about. TVL additionally drives automatic selection of the probe's third leg.

**[verified]** the gateway is self-serve with a free tier adequate for a demo, and the current-generation v3 subgraph exposes the needed price fields directly.

**Validity guard**: the run aborts if the three legs' product deviates from 1.0 by more than 1% (FR-003).

**Why the guard is necessary — and the honest caveat**: the product identity is *exact* for cross-rates derived from a single price source, but only *approximate* across three independently-priced AMM pools, which arbitrage holds together within roughly the fee band (~0.05–0.3%). The 1% check certifies the probe is currently arbitrage-tight. Since typical 24-hour moves (±1–5%) dwarf that band, the constraint holds for any economically meaningful move. State exactly this if challenged; do not claim the pool-based version is exact.

---

## D7. File-based baseline storage

**Decision**: A single `baselines.json`, keyed by a hash of (model, system prompt, data source, probe), committed to the repository.

**Rationale**: Baselines are five scalars each. A database would add a service dependency and a migration story for no benefit. Committing the file means a fresh clone reproduces the demo verdict without first running a multi-minute calibration.

**Key derivation is load-bearing**, not incidental: FR-015 requires that changing the model, the prompt, the data source, or the probe yields a different key. That key *is* the re-check trigger list — a stale baseline silently compared against a changed configuration would produce a confident and wrong verdict. Absent key ⇒ `NO_BASELINE`, never a fallback to the nearest match.

---

## D8. Concurrency to meet the 45-second budget

**REVISED 2026-07-26 — the original decision assumed a concurrency level that fails in practice.**

**Original decision**: run all 9 elicitations (reps=3) concurrently.

**What was measured**: 5-way concurrency returned `503`; roughly 1 request/second sequential drew `429`. The documented "30 req/min, 5 concurrent" is not what this account experiences in practice — treat it as inapplicable rather than a ceiling to plan against.

**Revised decision**: run elicitations **sequentially**, with exponential backoff on `429`/`503` (observed effective: 2 retries, base delay ~2–3s). Concurrency, if used at all, is 2-way at most and only as a stretch optimization once sequential is proven reliable.

**Measured**: a full sequential reps=3 workload (9 calls, real triangle prompt, temp=1.0) completed in **26.0s**, with one outlier call at 9.0s against a typical 2.0–2.3s. That fits SC-002's 45-second budget with real but not generous margin — a single retry-requiring call could push close to the limit.

**Revised SC-002 language**: the 45-second figure should be re-validated against whichever model is finally selected (D10) — the timing above is from `qwen2.5-omni`; latency on a Claude-tier mainnet model is unmeasured and may differ. Treat 45s as a target to re-confirm, not a proven number, until that run happens.

*Mitigation for calibration* (27–45 elicitations, sequential): unchanged from the original decision — this is explicitly not covered by the 45-second budget, and a progress indicator matters more than speed here.

---

## D9. Testing posture

**Decision**: Unit-test the pure core (`core.py`, `baseline.py`, `triangle.py`). Validate integration through the runnable scenarios in [quickstart.md](./quickstart.md) rather than mocked tests.

**Rationale**: The deterministic mathematics is where a silent error would be most damaging and least visible — a wrong LP or an off-by-one in the degrees of freedom produces plausible numbers that are simply incorrect. That deserves locked-down tests.

Integration is the opposite case. FR-004 forbids substituting synthetic data anywhere; a mocked test of `graph_client.py` would verify the mock and would additionally create the exact fallback code path the requirement exists to prevent. The honest validation is a real run against live sources, which is what quickstart provides.

---

## D10. Subject model: testnet's only chat model is unusable; mainnet required

**[verified 2026-07-26]** — supersedes any prior assumption that `qwen2.5-omni` (testnet's sole chat model, per D4) was an adequate subject.

**The finding.** On the actual production prompt shape (persona framing, "account for how X and Y are related" instruction, live-style market data block), `qwen2.5-omni` returned **the exact same answer 32 times in a row**, across every sampling parameter the OpenAI-compatible API exposes:

| Sweep | N | Result |
|---|---|---|
| temperature = 1.0 | 6 | flat |
| temperature = 1.6 | 4 | flat |
| temperature = 1.0, with numeric market data | 6 | flat |
| top_p = 0.95 (no temperature) | 4 | flat |
| top_p = 0.7 (no temperature) | 4 | flat |
| temperature = 1.2 + top_p = 0.9 | 4 | flat |
| temperature = 1.0 + presence_penalty = 1.0 | 4 | flat |

Every run: `{"p_XY_both_true": 0.2, "p_X_true_Y_false": 0.3, "p_X_false_Y_true": 0.3, "p_both_false": 0.2}`, byte-identical. Requests were verified non-cached — each carried a unique nonce and timestamp in the prompt text.

**This is not a general temperature failure.** An earlier, more abstract prompt ("two crypto price statements X and Y", no persona, no explicit correlation instruction) *did* produce real variance from the same model at temp=1.0 (`sd = 0.173`, n=3). Something specific to the production prompt's shape — plausibly a strongly memorized response template for correlation-aware financial forecasting — collapses this model onto one answer, and no sampling parameter reopens it.

**Cross-check against a known-good model, to isolate model from methodology.** The identical production prompt, run through the local `claude` CLI (Sonnet) 5 times sequentially:

```
rep 1: p_X_true_Y_false=0.43  p_X_false_Y_true=0.35   P(X≠Y)=0.78
rep 2: p_X_true_Y_false=0.40  p_X_false_Y_true=0.35   P(X≠Y)=0.75
rep 3: p_X_true_Y_false=0.44  p_X_false_Y_true=0.36   P(X≠Y)=0.80
rep 4: p_X_true_Y_false=0.42  p_X_false_Y_true=0.38   P(X≠Y)=0.80
rep 5: p_X_true_Y_false=0.45  p_X_false_Y_true=0.32   P(X≠Y)=0.77
```

`mean = 0.780, sd = 0.0212, std_error(n=5) = 0.0095` — exactly the shape the CI design requires: a stable mean with real, small, non-degenerate sampling spread. This confirms the prompt template and elicitation methodology are sound; the problem is specific to `qwen2.5-omni`.

**Decision**: fund a 0G **mainnet** account (~$20) and select a Claude-tier model from the 22 available there (`claude-opus-4-8` confirmed listed; `claude-sonnet-5` may also be available — re-check `/v1/models` at fund time). Testnet is no longer viable for the subject model, though it remains fine for everything else already proven (auth flow, endpoint shape, prompt parsing, attestation surface — see O1, O2).

**Before spending**: re-run the exact D10 methodology above (32-call sweep) against the selected mainnet model before committing further build time to it. The `claude` CLI result is strong evidence the *class* of model works, not proof the specific 0G-hosted deployment will — a hosted Claude model behind a router is a different serving stack than the local CLI.

**What does NOT need to change**: D1 (baseline-relative gating), D2 (t-distribution CI math), the elicitation methodology in D3, and the prompt template itself. All are validated by the Claude cross-check. Only the subject model changes.

**[RESOLVED 2026-07-26 — mainnet funded, subject model selected.]** The "select a Claude-tier model" plan above did not survive contact with the actual mainnet deployment. What was found, in order:

1. **Claude models (fable-5/opus-4-8/sonnet-5) and gpt-5.6-luna/sol/terra all share one provider** (`0x1F444c8A8D0b8e99A50e9f165806d28B01916E04`), which is `is_healthy: false` in `/v1/providers` and returns `403 BALANCE_INSUFFICIENT` regardless of how the ledger and provider sub-account are funded. Tested: funding via the portal's Advanced per-provider flow (2.00 0G confirmed allocated), general ledger deposit (3.00 0G confirmed "spendable on inference"), retrying after propagation delay, and calling through both the shared router and that provider's own dedicated satellite endpoint (see below). All failed identically. This provider looks broken on 0G's infrastructure side — not a client-side setup mistake — and no further time should go into re-funding it.
2. **A separate, unrelated trap along the way**: some portal-issued API keys are scoped to one provider's own satellite endpoint — a third-party gateway (`https://<name>.integratenetwork.work`) sitting in front of 0G, with a distinct path (`/v1/proxy/messages`), distinct auth (`Authorization: Bearer app-sk-<base64(message:signature)>`, not `x-api-key`), and its own balance cache independent of the main router's. Such a key gets a plain `401` on the shared router (`router-api.0g.ai`). Fix: use a general-purpose key from the main "Create key" flow, not the per-provider "Advanced" flow, when targeting the shared router.
3. **`glm-5.2`** has healthy providers (e.g. `0x7DCFe6AEa70350C2090041524c9B4A9262DCe87D`) and calls succeed with real TEE attestation (`TeeML`/TDX) — but it is a reasoning model that spends its *entire* `max_tokens` budget on hidden `reasoning_content` and never reaches a final answer: `finish_reason: "length"` at `max_tokens` = 150, 2000, and 4000 alike, with `reasoning_tokens` exactly equal to `max_tokens` every time. `reasoning_effort`, `thinking.disabled`, and `chat_template_kwargs.thinking=false` are all listed in `supported_parameters` but none of them changed this — the router does not forward them, the same failure shape as `qwen2.5-omni` ignoring `temperature` on testnet (D10 above).
4. **`deepseek-v4-flash`** — also a reasoning model, but its `enable_thinking: false` flag *is* honored (confirmed directly: `finish_reason` flips from `"length"` to `"stop"` when set). 3 healthy providers. **Selected as the subject model.**

D10 sweep re-run against `deepseek-v4-flash` on mainnet (n=3, temp=1.0, sequential, unique nonce per call — same methodology as the table above):

```
rep 0: P(X≠Y)=0.50
rep 1: P(X≠Y)=0.40
rep 2: P(X≠Y)=0.45
```

`mean = 0.45, sd = 0.05, std_error(n=3) = 0.0289`. Real, non-degenerate variance — verdict: **usable**. Total wall time 6.4s for 3 calls, well inside the 45s/reps=3 budget (SC-002), though this is n=3 for a quick go/no-go check; a fuller n=8 sweep per the original D10 methodology is still recommended before final calibration.

`ZG_MODEL=deepseek-v4-flash` is now the default in `.env.example` and `scripts/probe_0g.py`.

---

## D11. Attempted degradation demo: two honest attempts, two negative results

**[Attempted 2026-07-26, post-launch.]** Tried to reproduce a live `VETO` against `deepseek-v4-flash`'s
real calibrated baseline (`mean_disagreement_sum=1.484, std_dev=0.079, n=12`), per O5's mandate to validate
this once before ever claiming it in a demo.

**Attempt 1 — uniform mood/persona randomization.** System prompt instructed the model to silently adopt a
random emotional mood (panicked/euphoric/bored/paranoid) per question, with no memory of other questions.
Result: mean essentially unchanged (`1.483` vs baseline `1.484`), but `std_error` widened ~8x (`0.165` vs
typical `~0.02`). This *increases* noise without shifting the mean, which makes a significant result
*harder* to reach, not easier — a genuinely useful negative result, not just "didn't work."

**Attempt 2 — asymmetric fabricated narratives, the theoretically-motivated lever.** Each of the three
isolated contexts was given a different, mutually-inconsistent fabricated "recent move" framing (context AB
told WETH/USDC "just crashed -8% on panic selling"; context BC told USDC/WBTC "just spiked +12% on a short
squeeze, expected to reverse"; context AC given no special framing) — this is exactly the "different
premises to different contexts" mechanism O5 predicted was necessary. Run at reps=3: `PASS`, `p=0.249`,
trials `[1.68, 1.42, 1.54]` straddling the baseline rather than consistently below it. Re-run at reps=6 for
more statistical power (same intervention): `PASS`, `p=0.356` — *weaker*, not stronger, with a trial mean
(`1.535`) landing slightly *closer* to perfect coherence than the baseline, not further from it.

**Conclusion: does not reproduce, dropped per the project's own stated rule** ("if it does not reproduce,
drop the claim rather than weaken the confidence bar" — see O5 and the README's Honest Assessment section).
Two independent, real, live interventions against the actual shipped model — not a simulation — both failed
to produce a significant drift signal, one of them the specific mechanism theory predicted should work. This
does not mean the drift test itself is broken (the decision rule is unit-tested at all 5 boundaries,
including a synthetic VETO case, in `tests/unit/test_baseline.py`) — it means `deepseek-v4-flash` on this
particular prompt is more robust to these two specific interventions than expected, or a stronger/different
intervention is needed. No degraded-input demo mode is implemented in the shipped app as a result — this was
a standalone experiment (see the pattern in `experiments/`), never wired into `cohesion/`.

---

## Open items carried into implementation

| # | Item | Status | Mitigation |
|---|------|--------|-----------|
| O1 | Router exposes per-response attestation signature | **[unverified]** | Capture available verifiability metadata; sidecar only if time permits; never imply attestation that is absent |
| O2 | Provider account funded, testnet ledger opens and accepts inference | **PARTIALLY RESOLVED** ⚠️ | Auth, endpoint, and prompt parsing all confirmed on testnet (got past 401 to a real completion). **But see O6 — the testnet model itself is unusable**, so this account will not be the one used for the subject model in the final build. |
| O3 | Provider rate limits under calibration load | **RESOLVED** ⚠️ — worse than expected | 5-way concurrency → `503`; ~1 req/s serial → `429`. Revised to sequential + backoff (D8). Calibration (27–45 calls) will take noticeably longer than originally assumed; no longer treated as "probably fine," must be timed for real once the mainnet model is selected. |
| O4 | Hosted trading API key | **RESOLVED** ✅ | Key obtained 2026-07-26. Trading API is now the primary quote path (D5), unlocking the $7k track. Store as `UNISWAP_API_KEY` in `.env`. **Carries three hard qualification requirements — `FEEDBACK.md`, the feedback-form submission linking to it, and a README pointing at the integration lines.** |
| O5 | Whether a deliberate degradation reliably produces a veto (SC-007) | **RESOLVED — does not reproduce, claim dropped** ❌ | See D11. Two real live attempts against `deepseek-v4-flash`'s actual baseline (uniform mood randomization; asymmetric per-context fabricated narratives, the theoretically-motivated mechanism) both returned `PASS`, one at reps=3 and again at reps=6 for more power. Per the project's own rule, the claim is dropped rather than the confidence bar weakened. No degraded-input mode ships in `cohesion/`. |
| O6 | Subject model produces genuine sampling variance | **RESOLVED ✅** | See D10. `qwen2.5-omni` (testnet) and `glm-5.2` (mainnet, runaway reasoning) both ruled out; the Claude/gpt-5.6-luna provider on mainnet is broken infrastructure-side. `deepseek-v4-flash` confirmed working: `enable_thinking=false` honored, real variance (`sd=0.05`, n=3), 6.4s total. This is now `ZG_MODEL`. |

---

## Established, do not re-litigate

Carried forward from prior validation in this repository. These are settled inputs to the design:

- Models place **3–9% of belief mass on impossible worlds** under clean, isolated conditions — reproducible across 6+ runs.
- **Signalling stays ≤0.02**, so the measurement is not confounded by contexts affecting each other's marginals.
- **Data leakage suppresses the signal** (0.68× observed) — per-context slicing is mandatory.
- **Crude uniform corruption does not raise incoherence** (0.28× observed, the opposite of the hoped-for direction). Consistent lies are believed coherently. Only asymmetric corruption is expected to register, and that remains unvalidated (O5).
- **No evidence links incoherence to realized profit or loss.** FR-031 forbids implying otherwise.
- **A subject model must be checked for genuine sampling variance before it is trusted, independent of how capable it seems.** `qwen2.5-omni` looked reasonable in the single-call probe (Scenario 4) and only failed under repeated sampling (D10). One successful call proves parsing works; it does not prove the model is usable as a measurement subject.
