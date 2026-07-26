# Cohesion — Spec-Driven Hackathon Build Plan (5–8h)

**Project name: Cohesion.** *Does your agent's reasoning hold together?*
Verified unused in crypto (2026-07-25). Carries two true meanings at once: the physics sense (the force
binding a substance together) and the software sense (cohesion vs. coupling — a well-formed module's parts
belong together). Both land on exactly what is being measured. Rejected: *Gluon* (taken — Ergo stablecoin
protocol, an L2, a wallet service), *Glueball* (reads as derivative of Glue, a $1.41B-FDV L1),
*Presheaf* (clear and mathematically exact, but opaque to crypto judges).

## Process: Spec-Driven Development with Spec Kit

Spec Kit **is already installed** (`.specify/init-options.json` confirms `speckit_version 0.14.2`, integration
`claude` with `ai_skills: true`). This install uses the **skills integration**, not command files — so
`speckit-specify`, `speckit-plan`, `speckit-tasks`, `speckit-implement` are available directly via the Skill
tool in this session already, no install step and no restart risk. Minimal path only: specify → plan → tasks
→ implement (skipping clarify/checklist/analyze/converge, per decision).

No `.gitignore` fix is needed — nothing is written to `.claude/commands/` under this integration mode, so
there's nothing hidden. `.specify/` is untracked but not ignored, so a normal `git add` picks it up.
`specs/` doesn't exist yet; `speckit-specify` creates it.

**Timebox: 45 minutes total for specify + plan + tasks.** This is a hackathon, not a greenfield project, and
the research below already settles the architecture. The role of these three phases is to convert decisions
we have *already made* into reviewable artifacts — not to re-derive them. If any phase runs long, write the
artifact by hand and move on. `/speckit.implement` then runs against the task list in batches, with a commit
after each working chunk so there are fallback points if the demo breaks.

**Acceptance criteria use EARS form** (`WHEN <event> THE SYSTEM SHALL <response>`) for everything that gets
demoed — see the seed criteria in the Spec Seed section below.

Everything generated stays in the repo and gets committed.

---

## Context

ETHGlobal Lisbon 2026, submission due within ~24h. We have validated math but zero product.

**What exists:** `experiments/coherence_ab.py` proves the core phenomenon — an AI agent asked about three
correlated market propositions in *separated contexts* assigns 3–9% of belief mass to logically impossible
worlds. The LP (`incoherence_lp`), the analysis (`analyse`), and the
elicitation loop (`ask`) all work and are reusable.

**What's missing:** everything a judge can see, and all three sponsor integrations.

**Target outcome:** a swap-dapp-shaped dashboard: the user picks a normal swap (pair + amount), gets a real
Uniswap quote, and the **Execute button is gated by the coherence guard** — the system auto-constructs a
probe triangle around the swap pair, elicits the agent's beliefs in isolated contexts, and either passes the
trade or vetoes it when the agent has drifted off its calibrated baseline. Same engine exposed as an MCP server; second
demo beat shows Claude Code (with Uniswap's own MCP tooling + our `coherence_check` MCP enabled) vetoing its
own swap mid-conversation.

**Framing note (this resolved the demo's weakest point):** the triangle is NOT the trade. The trade is an
ordinary swap anyone makes; the triangle is *instrumentation built around it* — the guard picks a third
asset to close the cycle because a closed cycle is the smallest structure where belief consistency is
enforceable by arithmetic. If a judge asks "who trades a 1:1 loop?" — nobody; it's the probe, not the trade.

**Sponsor tracks (all three load-bearing):**

| Sponsor | Track | How it is load-bearing |
|---|---|---|
| **The Graph** | Best AI Tooling ($5k) | Live Uniswap v3 subgraph defines the triangle constraint; shipped as a reusable MCP server, which is exactly what the track asks for ("guardrail or auditor layer", "not a single end-user app") |
| **Uniswap** | Best API Integration ($7k) → fallback Stack Contribution ($3k) | The triangle *is* a real 3-leg swap cycle; QuoterV2 gives the executable quote that gets vetoed |
| **0G** | Best Infrastructure & Tooling ($4.5k) | Every context elicitation runs on 0G Compute; the certificate bundles TEE-attested responses. Their track literally lists "Verification, guardrail, or auditor layer for on-chain agent actions" as an example |

**The pitch:** 0G attestation proves *who spoke*. We prove *what they said is possible*.

---

## Do These First (async, before writing any code — all three are humans-or-clocks-gated)

1. ~~**Buy 0G on an exchange**~~ — **RESOLVED, no purchase needed.** Verified on-chain 2026-07-26:
   **10.0 0G on Galileo testnet** (chain 16602, `evmrpc-testnet.0g.ai`) against a 4 0G minimum
   (3 ledger + 1 provider). Mainnet balance is 0 — **target testnet**.
   *Correction:* an earlier note here claimed testnet was ruled out because the minimums are
   contract-level and identical there. The minimums claim was right; the conclusion was wrong —
   it assumed the 0.1/day faucet was the only funding route. A grant-funded balance breaks that.
   **Saves 30–90 min of exchange-withdrawal wait and ~$20.**
   Still unproven: that the ledger opens and a provider accepts the funds. Prove it with one
   end-to-end attested call before building on it.
2. **Register for a Uniswap Developer Platform API key** at https://developers.uniswap.org/dashboard.
   Issuance latency is unverified. If it arrives we target the $7k track; if not, the $3k track.
3. **Get The Graph API key** at https://thegraph.com/studio/apikeys/ (self-serve, instant, 100k free
   queries/month).

All keys go in `.env` (already gitignored): `GRAPH_API_KEY`, `ZG_API_KEY`, `ETH_RPC_URL` (Alchemy free tier),
optionally `UNISWAP_API_KEY`. Never hardcode them — the repo goes public for judging.

---

## Architecture

```
coherence/
  core.py          # LP incoherence + analyse        <- extracted verbatim from coherence_ab.py
  graph_client.py  # Uniswap v3 subgraph queries     <- The Graph
  uniswap.py       # QuoterV2 staticCall             <- Uniswap
  inference.py     # 0G Compute Router client        <- 0G
  triangle.py      # swap route -> 3 propositions + prompts
  baseline.py      # calibrate / load / drift verdict
  server.py        # FastAPI, SSE stream, serves web/
  mcp_server.py    # MCP tool: coherence_check(route, reps)
web/
  index.html       # single-page dashboard, no build step
```

Python throughout. The 0G Compute **Router** is OpenAI-compatible HTTP, so `openai` SDK with
`base_url="https://router-api.0g.ai/v1"` avoids needing the TypeScript SDK. (See risk R1 below for the
signature-verification caveat.)

**Two distinct models — keep these straight, it's the most confusable part of the design:**
- **The caller / orchestrator** — Claude Code (or the dashboard user) requesting a swap. Never the subject.
- **The subject under test** — the agent whose beliefs get probed in three isolated contexts. This runs on
  **0G Compute** (`inference.py`), selectable via a `model` argument. This is what keeps 0G load-bearing.

Demo narrative: *Claude Code is the orchestrator; the trading agent it would delegate capital to is the
0G-hosted model; the guard tests that agent before the swap.* A `--self-probe` experimental flag (MCP
`sampling/createMessage`, asks the calling client to answer the probes instead) is a stretch goal only —
client sampling support is unverified and it bypasses 0G, so it must never become the default path.

---

## The Triangle (this is the design's core)

The triangle is **constructed around the user's swap pair**, not fixed: for a swap X→Y, the guard picks a
third asset Z from a small liquid set (WBTC, USDT, DAI — highest-TVL pool wins) and closes the cycle
X/Y, Y/Z, Z/X. Default demo case: swap WETH→USDC, probe triangle **WETH → USDC → WBTC → WETH**. The
third-asset choice is also the hook for the multi-triangle roadmap line (sweep several Z's for stronger
constraints — sheaf-theoretic generalization; roadmap only, not built today).

Three binary propositions about the next 24h (for the default triangle):
- `A`: the WETH/USDC pool price ends HIGHER than now
- `B`: the USDC/WBTC pool price ends HIGHER than now
- `C`: the WBTC/WETH pool price ends HIGHER than now

Because the three ratios multiply to exactly 1, `P(A≠B) + P(B≠C) + P(A≠C)` **must equal 2.000** for any
coherent forecaster. This is not a modelling assumption — it is arithmetic.

**Pool-price honesty caveat (a sharp judge will probe this):** the identity is *exact* for cross-rates
derived from one price source (the old Binance version) but only *approximate* for three independent AMM
pools — each pool prices on its own, and their product stays ≈1 only because arbitrageurs hold it inside the
no-arb band (roughly the fee tier, ~0.05–0.3%). In principle all three pool prices could tick up together
within that band. Two consequences, both already handled but state them explicitly: (a) the 1% product sanity
check at run start is what certifies the triangle is currently tight; (b) since typical 24h moves (±1–5%)
dwarf the band, the constraint holds for any economically meaningful move — say exactly this if asked, don't
claim the pool version is exact. Prompts phrase the propositions on the pool price ratios as reported, which
is what the agent would actually act on.

This is a strict upgrade over the current Binance version: each leg is now an actual Uniswap pool the agent
would route through, so the vetoed trade is a real trade.

## Verdict Logic: Calibrated Baseline + Drift Detection

**The flaw this fixes.** Every model tested so far sits at 3–9% incoherence, *always*. If VETO fired
whenever the CI excludes 2.000, then at sufficient reps **every agent gets vetoed every time** — useless as
a gate, and it makes an honest PASS impossible to demo. Absolute coherence is not a bar anything currently
clears.

**So the gate fires on drift from the agent's own baseline, not on absolute deviation from 2.000.**

### Tier 1 — Calibration (one-time per configuration)
Run the probe at high reps (9–15) against the agent under known-good conditions. Store its baseline:
mean disagreement sum `μ₀` (e.g. 1.91), sample SD `σ₀`, and `n₀`. That is the agent's *normal*, published as
its health profile ("runs at 4.5% incoherence").

Persist to `baselines.json`, keyed by the tuple **(model, system-prompt hash, data source, triangle)**.
Change any element and the baseline is void — that keyed tuple is exactly the re-check trigger list
(model swap, prompt update, new feed, new route).

### Tier 2 — Monitoring (every check)
Run at normal reps, compare against the stored baseline via a **two-sample Welch's t-test**
(`scipy.stats.ttest_ind(..., equal_var=False)`) — variances between calibration and live runs need not match.
- Reading statistically indistinguishable from baseline → **PASS**
- Significantly worse than baseline → **VETO** (something changed)

### The 2.000 line stays — as context, not as the gate
It is what makes the number *mean* anything (why 1.91 = "4.5% of belief mass on impossible worlds" rather
than an arbitrary reading), and it is the theoretical floor the baseline is measured against. The UI shows
both: the 2.000 mark, the baseline band, and today's interval. The **decision** comes from drift.

### Sampling rules (unchanged)
- `reps` defaults to **3**, minimum for any variance estimate; slider spans 1–9.
- Per-context SE across reps, combined across the three independent contexts (variances add).
- Intervals use `t_{0.975, df}`, `df = reps − 1` — **not** a flat 2×SE. Critical values: 4.30 at reps=3,
  2.57 at reps=6, 2.31 at reps=9. A flat 2×SE at reps=3 would overclaim confidence, the exact sin the
  interval exists to prevent. `scipy.stats.t.ppf` is already a dependency.
- Below reps=3 there is no variance estimate: show a provisional point estimate labeled not-yet-confident,
  and render **neither** verdict.
- PASS text must carry its confidence: **"PASS — within baseline at 95% (reps=3)"**. A wide interval can
  PASS simply because we didn't look hard enough; absence of proof is not proof of absence.

### Headline metric is incoherence %
The LP already returns it as a fraction (`inc_dom`, e.g. 0.087 = "8.7% of this agent's belief mass sits on
logically impossible worlds"). Model-comparable, reads as a health score, implies no trade anyone would take.
Dollar figures are not reported anywhere in the UI or README.

### Demo consequence — this solves the PASS problem
No contrived "coherent model" needed. Calibrate the agent → run clean → **PASS** (within baseline) → poison
one context's data → **VETO** (drifted). Same agent, same protocol, both verdicts, nothing rigged.

**Leak discipline (critical — do not regress this):** each context sees only the two ratios relevant to it.
`market_block(m, ctx)` in `coherence_ab.py:58-73` already implements this; preserve the behaviour exactly.
An earlier run showed 0.68x because the third ratio leaked and let the model infer the constraint.

---

## Spec Seed (write this BEFORE letting the agent generate anything)

The `speckit-specify` input, drafted from the decisions already made (the template mandates prioritized,
independently-testable user stories — hand it these three rather than letting it invent its own):

> Build **Cohesion**, a reasoning health check for AI agents that gates trades before capital moves. It
> measures whether an agent's beliefs about correlated market variables could all be true at once, by
> eliciting probabilities in isolated contexts and testing via linear programming whether they can glue into
> a single joint distribution. Because every model carries some baseline incoherence, the pass/fail decision
> is made against that agent's own **calibrated baseline**, not against the theoretical ideal — the guard
> fires on *drift*, which is what makes it usable as a gate and what lets it detect silent model degradation.
> Constraints: live Uniswap v3 pool data from The Graph (never mocked), inference on 0G Compute, a browser
> dashboard plus an MCP server sharing one engine, and a check must complete in under ~45 seconds at reps=3.
>
> **P1 (viable alone) — calibrate an agent.** An operator selects an agent (model + system prompt) and a
> swap pair, and runs calibration: the system builds a probe triangle around the pair from live pool data,
> elicits the agent's forecasts in three isolated contexts at 9–15 reps each, and stores the resulting mean,
> standard deviation, and sample size as that agent's baseline health profile, keyed by model, prompt, data
> source, and triangle. The operator sees the agent's normal incoherence level (e.g. "4.5%"). This alone is
> useful: it is a published health score for an agent.
>
> **P2 — gate a swap against the baseline.** A user sets up an ordinary swap (pair + amount) in the
> dashboard, gets a real Uniswap quote, and clicks Execute — which is gated: the system runs a check at
> reps=3, streams in the three isolated forecasts with their 0G attestation stamps, and compares the result
> to the stored baseline with a two-sample test. Within baseline → PASS, Execute unlocks. Significantly
> worse → VETO, Execute stays locked. No stored baseline → no verdict at all, with a prompt to calibrate
> first. Every verdict displays its confidence level and reps count. (No on-chain send; the gate is the demo.)
>
> **P3 — agent-callable via MCP.** Another AI agent calls the same engine over MCP with a swap pair and
> receives a structured verdict (PASS/VETO/NO_BASELINE, incoherence %, disagreement sum, confidence interval,
> baseline comparison) it can act on programmatically — demoed in Claude Code alongside Uniswap's own MCP
> tooling, with the agent's own swap vetoed mid-conversation.

**EARS acceptance criteria** (the demoed behaviour — carry these into the spec verbatim):

- WHEN the user submits a swap pair and amount, THE SYSTEM SHALL construct a probe triangle containing that
  pair (choosing the highest-TVL third asset from a fixed liquid set), query live Uniswap v3 pool prices from
  The Graph, and reject the run if the product of the three ratios deviates from 1.0 by more than 1%.
- WHEN the coherence verdict is a veto, THE SYSTEM SHALL keep the Execute action disabled; WHEN the verdict
  is a pass, THE SYSTEM SHALL enable it.
- WHEN pool prices are retrieved, THE SYSTEM SHALL elicit a joint probability distribution from the agent in
  three isolated contexts, each run at least 3 times (reps≥3) so per-context variance is estimable, each
  context shown only the two ratios relevant to it.
- WHEN a context is elicited, THE SYSTEM SHALL record the 0G attestation metadata for each response.
- WHEN all reps across all three contexts have returned, THE SYSTEM SHALL compute the sum of pairwise
  disagreements, its standard error (combining the three per-context standard errors), and the incoherence %
  from the LP.
- WHEN a stored baseline exists for the current (model, prompt, data source, triangle), THE SYSTEM SHALL
  compare the run against it with a two-sample Welch's t-test and SHALL render VETO when the run is
  significantly worse than baseline at 95%, otherwise PASS.
- WHEN no baseline exists for the current configuration, THE SYSTEM SHALL refuse to render a verdict and
  SHALL prompt the operator to run calibration first.
- WHEN a verdict is rendered, THE SYSTEM SHALL display the confidence level and reps count alongside it
  (e.g. "PASS — within baseline at 95% (reps=3)").
- WHEN reps < 3, THE SYSTEM SHALL show a provisional point estimate labeled not-yet-confident and SHALL
  render neither VETO nor PASS.
- WHEN calibration is requested, THE SYSTEM SHALL run 9–15 reps per context and persist mean, SD, and n to
  `baselines.json` keyed by that configuration tuple.
- WHEN the operator sets the reps parameter between 1 and 9, THE SYSTEM SHALL run that many elicitations per
  context and report the averaged distribution with its confidence interval.
- WHEN any live data source is unavailable, THE SYSTEM SHALL fail visibly rather than substitute cached or
  synthetic data.

---

## Build Steps

Each step below is one `/speckit.implement` batch and **ends in a commit**. Never carry two unfinished steps
at once — every commit must leave the demo runnable, so that any point in the timeline is a safe fallback if
something later breaks.

### 0. Spec Kit artifacts (~45 min) → commit `chore: spec-kit specify/plan/tasks`
Run `speckit-specify` / `speckit-plan` / `speckit-tasks` (already installed) against the seed above. Commit
`.specify/` and `specs/` before writing any application code — they are timestamped evidence of how the AI
was directed.

### 1. The Graph (~40 min) → commit `feat(graph): live Uniswap v3 pool prices`
`graph_client.py`. Query the Uniswap v3 subgraph
(`gateway.thegraph.com/api/<KEY>/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV`) for the three
pools: `token0Price`, `token1Price`, `feeTier`, `liquidity`, `totalValueLockedUSD`, plus `poolDayDatas(first: 2)`
for the 24h change. Verify the product of the three ratios is ~1.0 — this is your sanity check that the
triangle is real. Replaces `fetch_market()` (Binance).

### 2. Core extraction (~50 min) → commit `feat(core): LP incoherence + CI + baseline drift`
`core.py`. Move `incoherence_lp`, `analyse`, `CONTEXTS`, `FORBIDDEN`, `PROP` out of `coherence_ab.py`
unchanged. Make `analyse` return a dict instead of printing. Add `confidence_interval()`: per-context standard
error of the disagreement-mass estimate across its reps, combined (variances add across independent contexts)
into an SE for the sum-of-disagreements statistic; returns the 95% t-interval (`t_{0.975, reps−1} × SE` via
`scipy.stats.t.ppf`). Add `baseline.py`: `calibrate()` (9–15 reps, persist mean/SD/n to `baselines.json`
keyed by model + prompt hash + data source + triangle), `load_baseline()`, and `drift_verdict()` running
`scipy.stats.ttest_ind(..., equal_var=False)` against the stored baseline → VETO / PASS / NO_BASELINE.
Requires `reps ≥ 3` to produce a CI at all; at reps<3 return an explicit "not enough samples" state
rather than a fake CI. Also `triangle.py` here: the WETH→USDC→WBTC→WETH route definition, the three
propositions, and the per-context prompt builder (porting `market_block`'s leak discipline from
`coherence_ab.py:58-73` to Graph-sourced pool data). This table + CI are the demo's punchline; build them
early.

### 3. Uniswap (~45 min) → commit `feat(uniswap): QuoterV2 route quotes`
`uniswap.py`. QuoterV2 `quoteExactInputSingle` via `staticCall` (mandatory — the Quoter reverts to return
data) on an Alchemy free RPC key. Quote each of the three legs for a fixed notional, producing the concrete
swap the guard will veto. Try the Trading API `POST /v1/quote` if the key arrived; otherwise the Quoter
contract alone satisfies the Stack Contribution track.

### 4. Server + dashboard (~2h) → **three commits**: `feat(server): SSE run endpoint`, then
`feat(web): gauge + verdict` (the punchline — commit it working before anything else), then
`feat(web): triangle + gauge`
`server.py`: FastAPI, one endpoint `GET /api/run?reps=N` streaming SSE events (`pools`, `quote`,
`context_result`, `verdict`). `reps` defaults to **3** (~35–45s, 9 parallel calls: 3 contexts × 3 reps) — the
minimum for a real confidence interval — and is settable 1–9 via a UI slider; at reps<3 the UI shows a
provisional point estimate labeled "not yet statistically confident," never a veto.

`web/index.html`: no build step, plain HTML/CSS/JS. Swap-dapp shape:
- Top: swap form — token pair (default WETH→USDC), amount, live Uniswap quote, and an **Execute button that
  starts disabled ("awaiting coherence check")**. No on-chain send is wired; the gate itself is the product.
- Below it: the probe triangle drawn around the chosen pair (three pools, live Graph prices, third asset
  labeled "auto-selected probe leg")
- Middle: three probability bars filling in as each isolated context's reps land, each stamped with its 0G
  attestation
- Then: a gauge showing three things at once — the hard **2.000** theoretical mark, the **stored baseline
  band** for this agent, and today's observed interval. Demo line: "it's not that it deviates from 2 — it
  always does. It's that it moved off its own baseline."
- Then: verdict — **red VETO** (Execute stays locked) when the run is significantly worse than baseline,
  **green PASS** (Execute unlocks) when within it, each stamped with confidence + reps
  ("PASS — within baseline at 95% (reps=3)"). Headline number is **incoherence %**.
- Bottom: the 6-possible-worlds table showing which worlds carry impossible belief mass — the *proof* the %
  is real. No dollar figures anywhere.
- A **Calibrate** button that runs 9–15 reps and stores the baseline; verdicts are refused until one exists.

### 5. 0G (~1h) → commit `feat(0g): inference via Compute Router + attestation capture`
`inference.py`. Swap the `claude -p` subprocess for the 0G Compute Router via the `openai` SDK. Capture and
surface whatever verifiability metadata the response carries (`verifiability: TeeML`, response ID, provider
address). Keep `claude -p` behind a `--provider` flag as the fallback path.

### 6. MCP server (~45 min) → commit `feat(mcp): coherence_check tool + SKILL.md`
`mcp_server.py`. One tool, `coherence_check(pair, amount, reps, model)`, returning the same structured
verdict the dashboard gets: coherent/incoherent, **incoherence % (headline)**, observed sum, the t-interval,
baseline comparison, per-context marginals, and attestation references. `model` selects
the 0G-hosted subject under test and defaults to a fixed 0G model. **Stretch only:** an experimental
`self_probe` flag using MCP `sampling/createMessage` to probe the *calling* agent instead — conceptually
purer but bypasses 0G and depends on unverified client support; build only if Step 6 lands early, never as
the default. This is what makes the Graph AI Tooling submission qualify as
*reusable tooling* rather than a single app. Include a `SKILL.md`. Then the **agent demo config** (~15 min,
part of this step): register our MCP + Uniswap's own MCP tooling (github.com/Uniswap/uniswap-ai, linked from
their prize page) in Claude Code, instruct the agent to always call `coherence_check` before any swap tool,
and capture the veto happening mid-conversation — this clip is the centerpiece of the P2 story and the
strongest possible evidence of reusability for The Graph's AI Tooling track.

### DEFERRED DECISION — PASS/VETO demo ladder (revisit after Step 4 or 5)
Deliberately not scheduled: the three-mode demo ladder (honest PASS via different model/system-prompt under
the same 3-probe protocol; hard-VETO via split-brain per-context poisoning — see `discussion_summary.md` §7).
Costs ~55–85 min incl. a mandatory validation run; touches the prompt builder (per-context data override) and
the UI (mode toggle). **Decide once core functionality works end-to-end.** Design constraint to honor now, at
zero cost: `triangle.py`'s prompt builder should accept its data block *per context* (it already must, for
leak discipline) so the override hook is trivial to add later.

### 6b. [OPTIONAL] Publish MCP on Smithery (~20 min, only if Step 6 lands early) → commit `chore: smithery.yaml`
Add `smithery.yaml`, run their publish CLI. Strengthens The Graph's "reusable, not a single app" claim with
an externally-verifiable public listing. **Not a qualification requirement for any track — drop silently if
it hits any signup/review friction.** Do not let this displace Step 7 or the demo video; those are the hard
requirements.

### 7. Submission (~1h) → commit `docs: README, FEEDBACK.md, architecture diagram`
README with an architecture diagram and explicit pointers to the lines implementing each integration
(0G asks for this; Uniswap says "make your README clearly point to the relevant contracts and lines of code").
**`FEEDBACK.md` plus the Uniswap Developer Feedback Form is a hard qualification requirement — do not skip it.**
Demo video under 3 min (0G's cap; The Graph wants 2–4 min — shoot for ~2:45).

---

## Suggested Clock

| Time | Task | Commits |
|---|---|---|
| 0:00 | Start 0G purchase + Uniswap key registration + Discord ask (async) | — |
| 0:00–0:45 | specify / plan / tasks against the seed | 1 |
| 0:45–1:25 | The Graph subgraph working | 1 |
| 1:25–2:15 | `core.py` + `triangle.py` + `baseline.py`, CI, drift test | 1 |
| 2:05–2:50 | Uniswap QuoterV2 | 1 |
| 2:50–4:50 | Server + dashboard (**the wow moment — protect this block**) | 3 |
| 4:50–5:50 | 0G integration | 1 |
| 5:50–6:50 | MCP server + SKILL.md + Claude Code agent demo config/capture | 1 |
| 6:50–7:10 | [OPTIONAL] Smithery publish — skip if no slack | 0–1 |
| 7:10–7:50 | README, FEEDBACK.md, demo video | 1 |
| 7:50–8:00 | Buffer (thin — if anything slips, cut Smithery first, then the agent-demo capture; the MCP server itself is the qualification) |

Spec Kit adds ~1h of ceremony up front. That is real cost against a 5–8h budget — the trade is judge-facing
evidence of AI direction plus a task list that keeps `/speckit.implement` from wandering. If the 45-minute
specify/plan/tasks timebox blows out, write the artifacts by hand and keep moving; the artifacts matter, the
ritual does not.

---

## Risks and Fallbacks

- **R1 — 0G Router may not expose the TEE signature to the caller** (unverified). Only the direct-provider
  TypeScript SDK path (`broker.inference.processResponse()`) definitely returns a verifiable signature.
  *Mitigation:* ship the Router path first. Only if time remains, add a small Node sidecar for true
  signature verification. Do not start with the TS SDK.
- **R2 — 0G tokens don't arrive in time.** *Mitigation:* `--provider claude` fallback keeps the demo alive;
  drop to two sponsors and say so honestly rather than faking attestation.
- **R3 — Dashboard eats the schedule.** *Mitigation:* the gauge (2.000 mark + baseline band + today's
  interval) plus the verdict banner is the single highest-value visual. Build it first; the triangle
  animation and the six-worlds breakdown are decoration.
- **R4 — the drift VETO might not fire on demo night.** With the baseline design, PASS is now easy (clean
  run vs. own baseline), but VETO depends on the poisoning actually moving the metric — and we have one
  validated counter-example where a *crude uniform* spoof moved it the wrong way (0.28×). *Mitigation:*
  the poisoning must be **asymmetric** (split-brain: different data per context), which is mechanically
  near-certain to break gluing since it feeds contradictory premises about the same leg. Validate it once
  before demoing; if it surprises us, drop attack mode and demo PASS + the baseline story alone. Never
  loosen the 95% bar to force a VETO.
- **R4b — calibration must happen before judging.** The baseline is a real run (9–15 reps, several minutes)
  and verdicts are refused without one. Bake it into demo prep, and commit `baselines.json` so a fresh
  clone reproduces the verdict.
- **R5 — Mocked data disqualifies the Graph submission** ("Mocked or static data does not qualify").
  Every demo path must hit the live subgraph. No cached-pool fallback, ever.

---

## Honesty Constraints (carry over from validation)

Established: the model places 3–9% mass on impossible worlds; signalling ≤0.02. Dollar figures are no
longer reported — incoherence % is the only metric.

**Not** established, so do not claim: that live market data increases incoherence (1.32x, within noise);
that poisoned oracle feeds are detected (the one test showed 0.28x — the *opposite*); that incoherence
predicts P&L.

Frame it as: *"coherent ≠ correct — we detect self-contradiction, not wrongness."* Pitch it as a pre-trade
sanity check on reasoning, never as an alpha generator.

---

## Verification

1. `python -m coherence.graph_client` — prints the three live pool prices; assert their product is within
   1% of 1.0.
2. `python -m coherence.uniswap` — prints a real quote for each leg.
3. `python -m coherence.inference --provider 0g` — prints one completion plus its attestation metadata.
4. `uvicorn coherence.server:app` → open `localhost:8000`, set up a WETH→USDC swap, confirm Execute starts
   disabled, run the check at the reps=3 default, confirm the full stream lands within ~45s, a confidence
   interval renders on the gauge, and the Execute gate matches the verdict (locked on veto, unlocked on
   PASS, locked on VETO).
5. With no baseline present, confirm the UI refuses a verdict and prompts for calibration. Click Calibrate,
   confirm `baselines.json` is written with mean/SD/n and the config key.
6. Re-run clean against that baseline → expect **PASS** ("within baseline at 95%"). Then re-run at reps=1
   and confirm a provisional estimate labeled not-yet-confident, with **neither** verdict rendered.
7. Enable split-brain poisoning on one leg and re-run → expect **VETO** (significantly worse than baseline).
   If it doesn't fire, the attack mode is not demo-ready — see R4.
7. Register `mcp_server.py` in Claude Code and call `coherence_check` end to end.
