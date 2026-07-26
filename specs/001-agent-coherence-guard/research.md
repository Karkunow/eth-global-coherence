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

**Decision**: Run all elicitations for a check concurrently (9 at reps=3), streaming each result to the client as it lands.

**Rationale**: Serial execution cannot meet SC-002. Concurrency also serves FR-028 directly — partial results become available naturally rather than requiring separate progress plumbing.

**[unverified]** provider rate limits (documented around 30 requests/minute, 5 concurrent) may throttle calibration, which issues 27–45 requests. *Mitigation*: bound concurrency with a semaphore and surface a progress indicator; calibration is an explicitly slower operation and is not covered by the 45-second budget, which applies only to gating checks.

---

## D9. Testing posture

**Decision**: Unit-test the pure core (`core.py`, `baseline.py`, `triangle.py`). Validate integration through the runnable scenarios in [quickstart.md](./quickstart.md) rather than mocked tests.

**Rationale**: The deterministic mathematics is where a silent error would be most damaging and least visible — a wrong LP or an off-by-one in the degrees of freedom produces plausible numbers that are simply incorrect. That deserves locked-down tests.

Integration is the opposite case. FR-004 forbids substituting synthetic data anywhere; a mocked test of `graph_client.py` would verify the mock and would additionally create the exact fallback code path the requirement exists to prevent. The honest validation is a real run against live sources, which is what quickstart provides.

---

## Open items carried into implementation

| # | Item | Status | Mitigation |
|---|------|--------|-----------|
| O1 | Router exposes per-response attestation signature | **[unverified]** | Capture available verifiability metadata; sidecar only if time permits; never imply attestation that is absent |
| O2 | Provider account funded | **RESOLVED** ✅ | 10.0 0G verified on Galileo testnet (chain 16602) vs a 4-token minimum. Target testnet; no mainnet purchase needed. Ledger-open and provider-acceptance remain unproven until Scenario 4 runs. |
| O3 | Provider rate limits under calibration load | **[unverified]** | Semaphore-bounded concurrency; calibration exempt from the 45s budget |
| O4 | Hosted trading API key | **RESOLVED** ✅ | Key obtained 2026-07-26. Trading API is now the primary quote path (D5), unlocking the $7k track. Store as `UNISWAP_API_KEY` in `.env`. **Carries three hard qualification requirements — `FEEDBACK.md`, the feedback-form submission linking to it, and a README pointing at the integration lines.** |
| O5 | Whether a deliberate degradation reliably produces a veto (SC-007) | **[unverified]** | Must be validated once before being demonstrated. A prior crude uniform-corruption test moved the metric the *wrong* way (0.28×), so the degradation must be **asymmetric** — different premises to different contexts — which breaks gluing mechanically rather than hopefully. If it does not reproduce, drop the claim rather than weaken the confidence bar. |

---

## Established, do not re-litigate

Carried forward from prior validation in this repository. These are settled inputs to the design:

- Models place **3–9% of belief mass on impossible worlds** under clean, isolated conditions — reproducible across 6+ runs.
- **Signalling stays ≤0.02**, so the measurement is not confounded by contexts affecting each other's marginals.
- **Data leakage suppresses the signal** (0.68× observed) — per-context slicing is mandatory.
- **Crude uniform corruption does not raise incoherence** (0.28× observed, the opposite of the hoped-for direction). Consistent lies are believed coherently. Only asymmetric corruption is expected to register, and that remains unvalidated (O5).
- **No evidence links incoherence to realized profit or loss.** FR-031 forbids implying otherwise.
