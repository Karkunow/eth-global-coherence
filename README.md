# 🔺🩺 Cohesion — A Reasoning Health Check for AI Agents

**ETHGlobal Lisbon 2026** — AI agents + verifiable inference + DeFi

> Advises whether an AI agent's reasoning has drifted from its own normal — before it moves your money.

**Team:** Iaroslav Karkunov — Telegram [@wknvw](https://t.me/wknvw) · X [@apocnab](https://x.com/apocnab)

**Live demo:** [https://94-130-105-233.nip.io/](https://94-130-105-233.nip.io/) — the six models already
calibrated in [baselines.json](./baselines.json) work out of the box for PASS/VETO checks. Calibrating a
*new* model on this shared instance requires your own funded 0G mainnet account and 0G API key (get one at
[pc.0g.ai](https://pc.0g.ai) after depositing 0G tokens) — paste it into the "Your own 0G API key" field at
the top of the page, since this deployment's own key is deliberately not spendable by every visitor.

---

## Architecture

One engine (`cohesion/orchestrator.py`), two entry points, three load-bearing sponsor integrations:

```mermaid
flowchart TB
    UI["Browser Dashboard<br/>web/index.html"]
    MCPC["MCP Client<br/>e.g. Claude Code"]

    SRV["FastAPI server<br/>cohesion/server.py<br/>(SSE)"]
    MCPS["MCP server<br/>cohesion/mcp_server.py<br/>coherence_check / _calibrate / _baselines"]

    UI --> SRV
    MCPC --> MCPS

    ORCH["orchestrator.py<br/>run_check() / run_calibration()<br/>the ONLY module that knows the full sequence"]
    SRV --> ORCH
    MCPS --> ORCH

    TRI["triangle.py<br/>probe construction,<br/>leak-safe per-context prompts"]
    CORE["core.py<br/>Incoherence Calculation,<br/>t-distribution confidence interval"]
    BASE["baseline.py<br/>baselines.json<br/>Healthcheck (Welch's t-test)"]
    ORCH --> TRI
    ORCH --> CORE
    ORCH --> BASE

    GRAPH[["The Graph<br/>Uniswap v3 subgraph<br/>live pool prices, TVL"]]
    ZG[["0G Compute Router<br/>3 isolated belief queries<br/>+ attestation metadata"]]
    UNI[["Uniswap Trading API<br/>quote + swap calldata<br/>QuoterV2 fallback"]]

    TRI -->|live prices, per-leg| GRAPH
    ORCH -->|sequential, backoff| ZG
    ORCH -->|quote + build tx| UNI

    MM(["User's own MetaMask<br/>signs + sends, client-side only"])
    UNI -.->|unsigned tx, opt-in| MM

    VERDICT{{"PASS / VETO / NO_BASELINE"}}
    CORE --> VERDICT
    BASE --> VERDICT
    VERDICT --> EXEC["Execute — advisory gate only<br/>(never blocks, never auto-signs)"]

    classDef thegraph fill:#6f4cff,color:#fff,stroke:#333,stroke-width:1px;
    classDef uniswap fill:#ff007a,color:#fff,stroke:#333,stroke-width:1px;
    classDef zg fill:#00d1b2,color:#000,stroke:#333,stroke-width:1px;
    class GRAPH thegraph
    class UNI,MM uniswap
    class ZG zg
```

**The Graph** (purple) supplies every live price the probe triangle is built from — never mocked. **Uniswap**
(pink) turns the check into a real, quotable, optionally-signable trade. **0G Compute** (teal) runs every
belief query the whole measurement depends on. Detail on each integration, with file/line pointers, is
in [How It's Made](#how-its-made) below.

---

## The Problem

Autonomous agents are starting to move real money. Before one does, you want to know something basic:
**are its beliefs even self-consistent, and has that changed since it was last known good?**

Hardware attestation — like 0G's TEE-sealed inference — proves *who spoke*: that this exact model produced
this exact output, unaltered. It says nothing about whether what was said hangs together, or whether it's
gotten worse. An agent can be perfectly honest, running unmodified, and still hold beliefs that describe a
world which cannot exist — and every model does, to some degree. **Cohesion measures that gap, and gates on
drift from an agent's own calibrated baseline, not against an impossible ideal of zero incoherence.**

---

## How It Works

### 1. Build a probe triangle around a real trade

When a user sets up a swap, Cohesion auto-selects a third asset (by TVL, from a fixed liquid set) to close
the cycle. For a WETH→USDC swap it might pick WBTC, giving the loop **WETH/USDC → USDC/WBTC → WBTC/WETH**.

The triangle is **not the trade** — it's instrumentation built around it. A closed cycle is the smallest
structure where belief consistency is enforceable by arithmetic rather than opinion.

### 2. The constraint is arithmetic, not opinion

Each leg gets a binary proposition about the next 24 hours:

| | Leg | Proposition |
|---|---|---|
| **A** | WETH/USDC | ends HIGHER than now |
| **B** | USDC/WBTC | ends HIGHER than now |
| **C** | WBTC/WETH | ends HIGHER than now |

Because the three ratios multiply to exactly 1 (the cycle returns to WETH), two of the eight combinations
are impossible — and every surviving world has **exactly two disagreeing pairs**:

| # | A | B | C | A≠B | B≠C | A≠C | Total | Possible? |
|---|---|---|---|---|---|---|---|---|
| 1 | ↑ | ↑ | ↑ | · | · | · | **0** | ❌ product would exceed 1 |
| 2 | ↑ | ↑ | ↓ | · | ✓ | ✓ | **2** | ✅ |
| 3 | ↑ | ↓ | ↑ | ✓ | ✓ | · | **2** | ✅ |
| 4 | ↑ | ↓ | ↓ | ✓ | · | ✓ | **2** | ✅ |
| 5 | ↓ | ↑ | ↑ | ✓ | · | ✓ | **2** | ✅ |
| 6 | ↓ | ↑ | ↓ | ✓ | ✓ | · | **2** | ✅ |
| 7 | ↓ | ↓ | ↑ | · | ✓ | ✓ | **2** | ✅ |
| 8 | ↓ | ↓ | ↓ | · | · | · | **0** | ❌ product would fall below 1 |

Since the disagreement count is the constant 2 in every possible world, its expectation is 2 regardless of
how uncertain the forecaster is:

> **E[disagreements] = P(A≠B) + P(B≠C) + P(A≠C) = 2.000**

An agent landing below 2.000 isn't pessimistic or badly calibrated — it is assigning positive probability
to rows 1 and 8, worlds that cannot occur. In practice, real models never hit exactly 2.000; every model
carries some baseline incoherence (we measured 25–27% for our subject model, `deepseek-v4-flash`, on this
prompt — see [baselines.json](./baselines.json)). That's why gating happens against the agent's **own**
calibrated normal, not against the theoretical ideal.

### 3. Ask in isolation

Cohesion queries the three pairwise forecasts in **three separate, isolated inference calls** — a fresh
0G Compute request per context, never a shared conversation. Each context is shown only the two ratios
relevant to it ([cohesion/triangle.py](./cohesion/triangle.py)'s `build_context_slice`), so no single call
contains enough information to infer the third leg or the closed-cycle constraint.

The exact prompt template ([cohesion/triangle.py](./cohesion/triangle.py)'s `PROMPT_TEMPLATE`), filled in
here for context `(A,B)` with live mainnet prices:

```
You are a crypto market analyst producing a calibrated joint forecast.
RELEVANT RATIOS:
  WETH/USDC = 1882.03
  USDC/WBTC = 1.55509e-05

Consider these two statements about the next 24 hours:
  X = the WETH/USDC price ratio 24 hours from now is HIGHER than it is right now
  Y = the USDC/WBTC price ratio 24 hours from now is HIGHER than it is right now

Give your joint probability distribution over the four possible outcomes.
Account for how X and Y are related to each other.

Reply with ONLY a JSON object, no prose, no markdown fence:
{"p_XY_both_true": <float>, "p_X_true_Y_false": <float>, "p_X_false_Y_true": <float>, "p_both_false": <float>}
The four numbers must sum to 1.0.
```

A real response to this prompt (`0gm-1.0-35b-a3b`, live):

```json
{"p_XY_both_true": 0.24, "p_X_true_Y_false": 0.26, "p_X_false_Y_true": 0.26, "p_both_false": 0.24}
```

That's this context's contribution to `disagreement_sum`: `p_X_true_Y_false + p_X_false_Y_true` = `0.26 + 0.26`
= `0.52` — one of the three addends that should sum to `2.000` across all three contexts (see below).
`(B,C)` and `(A,C)` are built the same way, each blind to the leg not in its pair.

### 4. Measure the incoherence

A linear program ([cohesion/core.py](./cohesion/core.py)'s `incoherence_lp`) asks whether those three
pairwise answers can be marginals of *any* single joint distribution over the six possible worlds. It
maximizes the belief mass that can be assigned consistently; whatever cannot be placed anywhere is the
**incoherence %** — the share of the agent's belief that lives in no possible world.

### 5. Compare to the agent's own baseline, then advise

A one-sided Welch's t-test ([cohesion/baseline.py](./cohesion/baseline.py)'s `compute_verdict`) compares
the live reading against a stored, previously-calibrated baseline for that exact model/prompt/pair. **The
system advises, it never blocks**: on `PASS`, the trade proceeds with no friction; on `VETO` (significantly
worse than baseline) or `NO_BASELINE`, the UI requires an explicit, deliberate acknowledgement before the
Execute action unlocks — but it always unlocks eventually, because coherence is a necessary, not sufficient,
condition for sound reasoning. Blocking would assert more than the measurement supports.

---

## How It's Made

**Stack:** Python throughout — FastAPI with Server-Sent Events for the streaming dashboard
([cohesion/server.py](./cohesion/server.py)), `scipy.optimize.linprog` for the coherence LP,
`scipy.stats.t`/`ttest_ind_from_stats` for confidence intervals and the drift test, `httpx` for The Graph
and the Trading API, `web3.py` for the QuoterV2 fallback, and a stdio MCP server
([cohesion/mcp_server.py](./cohesion/mcp_server.py)) exposing the identical engine as three callable tools.
Frontend is plain HTML/CSS/JS with no build step, consuming the SSE stream directly.

### The core: a linear program over possible worlds

Three binary propositions give 8 combinations, but the price identity forbids two, leaving 6 possible
worlds. The LP asks: does there exist a probability distribution over those 6 worlds whose pairwise
marginals match what the agent actually said? We maximize total assignable mass subject to marginal
constraints; if the optimum falls below 1.0, the shortfall *is* the incoherence %.

### Statistical honesty

Confidence intervals use a real **t-distribution critical value** (`t_{0.975, df}`), not a flat 2×SE —
at reps=3 the critical value is 4.30, not ≈2.0, which matters a lot at small sample sizes
([cohesion/core.py](./cohesion/core.py)'s `confidence_interval`, unit-tested in
[tests/unit/test_core.py](./tests/unit/test_core.py)). Below 3 reps per context, no variance estimate
exists at all, so the system reports `INSUFFICIENT_SAMPLES` and renders no verdict rather than force one.
The drift test itself uses `scipy.stats.ttest_ind_from_stats` — the summary-statistics form of Welch's
t-test — since the stored baseline keeps only (mean, std_dev, n), not raw samples.

### Partner integrations — all load-bearing

**The Graph** ([cohesion/graph_client.py](./cohesion/graph_client.py)) supplies the live data the entire
constraint depends on: querying the Uniswap v3 subgraph via the decentralized gateway for `token0Price`,
`token1Price`, `feeTier`, `liquidity`, and `totalValueLockedUSD` across the three probe pools, trying both
token orderings since the subgraph's `token0`/`token1` address-sort order is arbitrary and doesn't match
our semantic direction. TVL also drives auto-selection of the triangle's third leg
(`pick_third_asset`, [cohesion/triangle.py](./cohesion/triangle.py)). A guard rejects the run if the three
legs don't multiply to within 1% of 1.0 — that check certifies the triangle is currently arbitrage-tight,
which is what makes the constraint valid on independently-priced AMM pools rather than clean cross-rates.

**Uniswap** ([cohesion/uniswap.py](./cohesion/uniswap.py)) turns the check into a gated, real trade. The
Trading API (`POST /v1/quote`, `x-api-key` auth) is the primary path — required for the $7k API Integration
track's qualification bar of "a valid API key from the Uniswap Developer Platform" — with QuoterV2's
`quoteExactInputSingle` via `.call()` (a genuine static call, not a sent transaction — the quoter is
non-view by design and reverts to return its data) as a live fallback. See
[FEEDBACK.md](./FEEDBACK.md) for a real integration issue found and reported during this build: the Trading
API alternates unpredictably between a classic-route response and a completely differently-shaped
UniswapX/Dutch-auction order response for the same request, unless `protocols: ["V3"]` is set.

**This isn't just calldata construction — it's a verified, mined, successful swap.** The dashboard's wallet
flow (connect MetaMask → approve Permit2 on-chain → sign the EIP-712 permit → send) was run end to end on
Ethereum mainnet:
[`0xde7d3fbdee59d9677551fd00988ea2ab1feecd80ce2762c0b81164d22b4ccc03`](https://etherscan.io/tx/0xde7d3fbdee59d9677551fd00988ea2ab1feecd80ce2762c0b81164d22b4ccc03) —
`0.0001 WETH → 0.188143 USDC`, block 25617169, `status: success`, routed through Uniswap's Universal Router
with a real Permit2 signature. No custody, no server-side key — the signature and the broadcast both
happened in the user's own wallet.

**0G Compute** ([cohesion/inference.py](./cohesion/inference.py)) runs every belief query, sequentially
with exponential backoff — 5-way concurrency triggers `503`s and ~1 req/s serial triggers `429`s on 0G's
router, so this is deliberately a plain loop, not `asyncio.gather`. Each response's attestation metadata
(provider address, response ID, verifiability) is captured and surfaced per-sample in the UI, honestly
labelled `"reported"` rather than `"verified"` when no cryptographic signature is present in the response.
Selecting a usable subject model took real trial-and-error against the live mainnet router: several Claude
models and a GLM reasoning model turned out to sit on an unhealthy provider or burn their entire token
budget on hidden reasoning with no way to disable it; `deepseek-v4-flash` was the model that actually
produced real sampling variance end to end (see `research.md`'s D10 for the full investigation).

### Two models, kept strictly separate

- **Caller / orchestrator** — Claude Code, the dashboard user, or any MCP client requesting a check. Never
  the subject.
- **Subject under test** — the agent named by the `model` argument, whose beliefs get probed on 0G Compute.

### Hacky bits worth mentioning

1. **Process-isolated querying, not conversation discipline.** The measurement only means anything if the
   agent genuinely cannot see its other answers. Each of the three contexts is a fully independent inference
   call, never a shared conversation — instructing a single conversation to "answer independently" would be
   unverifiable.

2. **A leak bug that became a design principle.** An early, cruder prompt showed incoherence *decreasing*
   when given the whole triangle's prices at once (0.68×) — the model could infer the closed-cycle
   constraint and enforce consistency it wouldn't otherwise have. `build_context_slice` now slices the data
   block per-context by construction, not by convention, and this is unit-tested.

3. **A price-direction bug the product check alone couldn't catch.** `graph_client.py`'s leg prices were
   briefly inverted (WETH/USDC showing `0.000532` instead of `~1880`) — the three-leg product still passed
   its 1% tolerance check throughout, because a *consistently* inverted convention also telescopes to 1.
   Caught only by adding a CLI (`python -m cohesion.graph_client`) and inspecting the actual displayed
   numbers against a known-good Trading API quote, not by trusting the product check alone.

4. **No mocked-data fallback, anywhere.** If The Graph, 0G, or the quote is unavailable, the run fails
   visibly. A cached-price fallback would have been trivial and would have quietly invalidated every claim
   this project makes.

**Same engine, two surfaces.** The dashboard (`server.py`) and the MCP server (`mcp_server.py`) both call
`orchestrator.run_check()`/`run_calibration()` directly, with zero decision logic of their own — so the two
interfaces return identical verdicts by construction, not by discipline. Verified live: the same
model/pair/reps through both `GET /api/check` and the MCP `coherence_check` tool resolved to the same
stored baseline and produced the same verdict shape.

### MCP tools (agent-facing)

Three tools, stdio, server name `cohesion` — full schemas in
[contracts/mcp-tools.md](./specs/001-agent-coherence-guard/contracts/mcp-tools.md). A caller (e.g. Claude
Code) is never the subject being measured — the `model` argument names the agent under test, which is not
necessarily the caller itself.

**`coherence_baselines()`** — lists what's already calibrated. Real call, this session:
```json
{"baselines": [
  {"model": "0gm-1.0-35b-a3b", "pair": ["WETH","USDC"], "third": "WBTC",
   "mean_incoherence": 0.2235, "mean_disagreement_sum": 1.580, "std_dev": 0.1254, "n": 12,
   "calibrated_at": "2026-07-26T06:13:10Z"},
  "... 5 more models"
]}
```

**`coherence_check(pair, amount, model, reps)`** — the gate. Real call against `0gm-1.0-35b-a3b`, reps=3:
```json
{
  "outcome": "PASS",
  "reading": {"incoherence": 0.24, "disagreement_sum": 1.567, "ci_low": 1.161, "ci_high": 1.972, "reps": 3},
  "baseline": {"mean_incoherence": 0.2235, "mean_disagreement_sum": 1.580, "std_dev": 0.1254, "n": 12},
  "p_value": 0.468, "confidence": 0.95, "requires_acknowledgement": false
}
```

**`coherence_calibrate(pair, model, reps)`** — establishes a baseline (27–45 calls, minutes not seconds);
returns `{"stored": true, "key": ..., "mean_incoherence": ..., "n": ..., "calibrated_at": ...}`, or
`{"stored": false, "reason": "BASELINE_EXISTS", ...}` if one already exists and `overwrite` isn't set.

The intended agent pattern: *"Before executing any swap, call `coherence_check`. If the outcome is `VETO`
or `NO_BASELINE`, do not execute — report the verdict and stop."* — an agent vetoing its own trade with no
human intervening.

---

## Sponsor Fit

| Sponsor | Track | How it is load-bearing |
|---|---|---|
| **The Graph** | Best AI Tooling | Live Uniswap v3 subgraph defines the triangle constraint; shipped as a reusable MCP server ("guardrail or auditor layer", not a single app) |
| **Uniswap** | Best API Integration | Trading API is the primary executable-quote path for the gated swap, with QuoterV2 as a live fallback; see [FEEDBACK.md](./FEEDBACK.md) |
| **0G** | Best Infrastructure & Tooling | Every query runs on 0G Compute; attestation metadata is captured and honestly labelled per-sample |

---

## Honest Assessment

**Established, live on mainnet:** every model calibrated so far places a meaningful share of belief mass on
logically impossible worlds when its answers are separated across isolated contexts — reproducible, never
zero, and different model to model. Current baselines (`baselines.json`, WETH-USDC-WBTC triangle):

| Model | Incoherence | disagreement_sum (target 2.0) | std_dev | n |
|---|---|---|---|---|
| `0gm-1.0-35b-a3b` | 22.4% | 1.580 | 0.125 | 12 |
| `0gm-1.0-35b-a3b-sia` | 24.0% | 1.533 | 0.225 | 12 |
| `deepseek-v4-flash` | 25.3% | 1.502 | 0.038 | 9 |
| `deepseek-v4-pro` | 28.4% | 1.440 | 0.133 | 9 |
| `qwen3-vl-30b` | 40.0% | 1.262 | 0.064 | 12 |
| `hy3` | 40.6% | 1.253 | 0.116 | 12 |

**A lower incoherence % is not the same as a "better" or "smarter" model — it is not a leaderboard of model
quality, only of internal self-consistency under this specific probe.** `deepseek-v4-flash` was the model
this project validated most thoroughly (see below) and sits mid-table, not first. Reproducible: a second
independent 9-rep run against it landed at `disagreement_sum=1.473` (95% CI `[1.422, 1.525]`), clearly
overlapping its own stored baseline. Signalling (max marginal spread across contexts) stays low across all
six, so the measurement is clean.

**Not established — and not claimed:**
- That a deliberate degradation reliably produces a `VETO`. A prior crude uniform-corruption test on an
  earlier prompt version moved the metric the *wrong* direction (0.28×) — a consistent lie gets coherently
  believed. This project does not ship a degraded-input demo mode; if we can't reproduce a real veto
  honestly, we don't fake one.
- That incoherence predicts P&L.

**The framing:** *coherent ≠ correct.* We detect self-contradiction and drift from an agent's own normal,
not wrongness. Like a compiler type-check — passing doesn't prove your program correct, but failing proves
something changed. Cohesion is a pre-trade sanity check on reasoning, never an alpha generator, and every
surface says so explicitly (see the `VETO` warning copy in `web/index.html`).

**One more limit worth stating:** coherence catches *fragmented* compromise (asymmetric prompt injection, a
split-brain data feed), not *uniform* compromise. An agent biased consistently in one direction passes the
check while still being wrong.

---

## Mathematical Background

- **Boole (1854)** — conditions on probability distributions
- **de Finetti (1931)** — the Dutch book theorem: coherence ⟺ no guaranteed loss
- **Vorobyev (1962)** — gluing conditions for marginals
- **Bell / Fine (1964–1982)** — contextuality in quantum foundations
- **Abramsky–Brandenburger (2011)** — sheaf-theoretic generalization
- **Abramsky–Barbosa–Mansfield (2017)** — contextual fraction via linear programming

The three context tables form a **presheaf**; coherence is precisely the question of whether it glues into a
**sheaf**. This is the same machinery used to analyze Bell inequalities, applied to AI agent beliefs.

---

## Repository

```
cohesion/
  core.py          # incoherence calculation + t-distribution CI + reading assembly    (pure, unit-tested)
  triangle.py       # probe construction, propositions, leak-safe prompts     (pure, unit-tested)
  baseline.py        # key derivation, atomic storage, drift-verdict decision  (unit-tested)
  graph_client.py     # live Uniswap v3 pool data                              <- The Graph
  uniswap.py           # Trading API quote + QuoterV2 fallback                  <- Uniswap
  inference.py          # 0G Compute Router client + attestation capture        <- 0G
  orchestrator.py        # run_calibration() / run_check(), shared by both interfaces
  server.py                # FastAPI, SSE endpoints, serves web/
  mcp_server.py             # stdio MCP: coherence_check / _calibrate / _baselines
web/
  index.html         # single-page dashboard (calibrate + trade/gate), no build step
tests/unit/
  test_core.py        # LP, CI, six-worlds enumeration
  test_baseline.py      # key derivation, atomic write, all 5 verdict boundaries
scripts/
  probe_0g.py           # standalone 0G connectivity + sampling-variance sweep
specs/                 # Spec Kit artifacts (spec, plan, tasks, research, contracts)
experiments/          # day-one validation runs (first hours of the event)
```

## Running It

### Prerequisites — this needs real credentials, not just a clone

`cohesion/config.py` loads `.env` and refuses to start if anything's missing (`RuntimeError` naming every
missing var) — there is deliberately no partial/degraded mode, per the no-mocked-data posture above. Four
keys need to be obtained and filled into `.env` before anything works; everything else in `.env.example` is
already a correct, working default and shouldn't be changed.

| Variable | Get it from | Notes |
|---|---|---|
| `GRAPH_API_KEY` | [thegraph.com/studio/apikeys](https://thegraph.com/studio/apikeys/) | Self-serve, instant. Free tier (100k queries/month) is plenty. |
| `UNISWAP_API_KEY` | Uniswap Developer Platform dashboard | Self-serve; issuance latency has varied. Required for the primary quote path — QuoterV2 is only a fallback. |
| `ETH_RPC_URL` | Any RPC provider (e.g. Alchemy free tier) | Only exercised if the Trading API is unreachable and it falls back to QuoterV2. |
| `ZG_API_KEY` | [pc.0g.ai](https://pc.0g.ai) mainnet portal, **after depositing real 0G tokens into a ledger** | The slow one — budget real time for the token purchase/deposit before the key becomes usable. Must be a general-purpose key from the main "Create key" flow, not the per-provider "Advanced" flow (that issues an app-scoped key that 401s against the shared router). |

**Don't change `ZG_MODEL`** from the shipped default (`deepseek-v4-flash`) without re-reading the comment
block above it in `.env.example` — most other 0G-hosted models were tested and ruled out for this project:
several sit behind an unhealthy provider (`BALANCE_INSUFFICIENT` regardless of funding), and reasoning models
like `glm-5.2` burn their entire token budget on hidden `reasoning_content` and never emit a parseable answer
unless `enable_thinking: false` is honored — which only `deepseek-v4-flash` does reliably (see `research.md`
D10 for the full investigation).

Without all four keys correctly set, nothing runs — not the dashboard, not the MCP server, not the CLI
entry points. There is no cached/offline demo mode.

```bash
cp .env.example .env    # fill in GRAPH_API_KEY, UNISWAP_API_KEY, ETH_RPC_URL, ZG_API_KEY
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/unit -v    # 20/20, pure math + baseline logic, no network needed — works without .env
uvicorn cohesion.server:app --port 8000
```

Open `localhost:8000`. The repo ships a real calibrated baseline (`baselines.json`, `deepseek-v4-flash` /
WETH-USDC-WBTC), so you can run a check against it immediately without recalibrating first — default is 3
reps per context (~35s), the calibrate slider goes to 9–15 for a fresh baseline.

**MCP:** `.mcp.json` registers `cohesion` for Claude Code (`python3 -m cohesion.mcp_server`, stdio). See
[contracts/mcp-tools.md](./specs/001-agent-coherence-guard/contracts/mcp-tools.md) for the tool schemas.

### Reproducing the original day-one validation

```bash
cd experiments
python3 -m venv venv
./venv/bin/pip install scipy numpy
./venv/bin/python coherence_test.py 4    # baseline, 4 reps
./venv/bin/python coherence_ab.py 5      # A/B blind vs grounded, 5 reps
```

Uses the local `claude` CLI as the model under test. Each run ~5–10 minutes. This was the first-hours
validation that motivated the whole project — the shipped system uses 0G Compute, not the local CLI, as its
subject model.

---

**Builder:** Slava Karkunov · karkunow@gmail.com
**Event:** ETHGlobal Lisbon 2026 (July 24–26)
