# 🔺🩺 Cohesion — A Reasoning Health Check for AI Agents

**ETHGlobal Lisbon 2026** — AI agents + verifiable inference + DeFi

> Health check proving an AI agent's beliefs are self-contradictory — before it moves your money.

---

## The Problem

Autonomous agents are starting to move real money. Before one does, you want to know something basic:
**are its beliefs even self-consistent?**

Hardware attestation — like 0G's TEE-sealed inference — proves *who spoke*: that this exact model produced
this exact output, unaltered. It says nothing about whether what was said hangs together. An agent can be
perfectly honest, running unmodified, and still hold beliefs that describe a world which cannot exist.

**Cohesion measures that gap.**

---

## How It Works

### 1. Build a probe triangle around a real trade

When an agent is about to execute a swap, Cohesion auto-selects a third asset to close the cycle. For a
WETH→USDC swap it picks WBTC, giving the loop **WETH/USDC → USDC/WBTC → WBTC/WETH**.

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

With three binary values that aren't all equal, exactly two share a value and one differs — so the pairs
always split into one agreeing and two disagreeing. Never 1, never 3.

Since the count is the constant 2 in every possible world, its expectation is 2 regardless of how uncertain
the forecaster is:

> **E[disagreements] = P(A≠B) + P(B≠C) + P(A≠C) = 2.000**

An agent landing at 1.84 isn't pessimistic or badly calibrated. It is assigning positive probability to
rows 1 and 8 — worlds that cannot occur.

### 3. Ask in isolation

Cohesion elicits the three pairwise forecasts in **three separate, isolated conversations**. The agent never
sees what it said elsewhere — exactly how multi-agent pipelines actually fragment reasoning. Each context is
shown only the two ratios relevant to it, so no single conversation contains enough information to notice
the constraint.

### 4. Measure the incoherence

A linear program asks whether those three answers can be marginals of *any* single joint distribution over
the six possible worlds. It maximizes the belief mass that can be assigned consistently; whatever cannot be
placed anywhere is the **incoherence %** — the share of the agent's belief that lives in no possible world.

Not "this looks risky." A number, derived from the agent's own stated probabilities.

### 5. Gate the trade

The verdict gates execution. Incoherent → the swap is blocked before capital moves.

---

## Use Cases

1. **Pre-execution hook** — block the trade before it fires if the agent's beliefs contradict.
2. **Coherence certificate** — vaults and DAOs require a signed, fresh proof before accepting agent txs.
3. **Fleet monitoring** — alert when a deployed agent's incoherence drifts after a model or feed change.
4. **Silent-degradation canary** — detect when a hosted model quietly gets worse, with no ground truth needed.

**Cadence:** per-trade for whales, per-hour for fleets, always on change (model swap, prompt update, new
data feed, regime shift).

---

## How It's Made

**Stack:** Python throughout — FastAPI with Server-Sent Events for the streaming dashboard,
`scipy.optimize.linprog` for the coherence LP, `scipy.stats.t` for confidence intervals, `web3.py` for
contract calls, and a stdio MCP server exposing the same engine as a callable tool. Frontend is plain
HTML/CSS/JS with no build step, consuming the SSE stream directly.

### The core: a linear program over possible worlds

Three binary propositions give 8 combinations, but the price identity forbids two, leaving 6 possible
worlds. The LP asks: does there exist a probability distribution over those 6 worlds whose pairwise
marginals match what the agent actually said? We maximize total assignable mass subject to marginal
constraints; if the optimum falls below 1.0, the shortfall *is* the incoherence %.

### Statistical honesty

Verdicts are gated on a **95% t-interval excluding 2.000** — `t_{0.975, df} × SE`, not a flat 2×SE. With
only 3 reps per context, a flat threshold would overclaim confidence (the critical value is 4.30 at reps=3
versus 2.31 at reps=9). Below 3 reps no variance estimate exists, so the system refuses to issue a veto at
all. "No significant violation at this confidence" is a valid, honestly-reported outcome — we never force a
verdict.

### Partner integrations — all load-bearing

**The Graph** supplies the live data the entire constraint depends on. We query the Uniswap v3 subgraph via
the decentralized gateway for `token0Price`/`token1Price`, `feeTier`, `liquidity`, `totalValueLockedUSD`,
and `poolDayDatas` across the three probe pools. Without live pool prices there are no propositions to
elicit beliefs about. TVL also drives auto-selection of the triangle's third leg. A guard rejects the run if
the three ratios don't multiply to within 1% of 1.0 — that check certifies the triangle is currently
arbitrage-tight, which is what makes the constraint valid on independently-priced AMM pools rather than
clean cross-rates.

**Uniswap** turns an abstract check into a gated trade. Each leg is quoted through QuoterV2 via
`staticCall` — mandatory, since the Quoter is non-view by design and reverts to return its data, the single
most common integration mistake. The quote makes the veto concrete: a real, executable route with real
amounts and fees, blocked at the Execute button.

**0G Compute** runs every belief elicitation. Rather than pulling in the TypeScript SDK, we point the
standard `openai` Python SDK at 0G's OpenAI-compatible Compute Router via `base_url`, keeping the entire
stack in Python and reusing our existing elicitation code unchanged. Each response's attestation metadata is
captured and surfaced per-context in the UI. This is what makes the incoherence proof unforgeable — without
it, a skeptic could reasonably say we fabricated the agent's answers.

### Two models, kept strictly separate

- **Caller / orchestrator** — Claude Code or the dashboard user requesting a swap. Never the subject.
- **Subject under test** — the agent whose beliefs get probed, running on 0G Compute.

The demo narrative: *Claude Code is the orchestrator; the trading agent it would delegate capital to is the
0G-hosted model; the guard tests that agent before the swap.*

### Hacky bits worth mentioning

1. **Subprocess-per-context isolation.** The measurement only means anything if the agent genuinely cannot
   see its other answers. Rather than trusting conversation-history management, each elicitation is a fully
   independent inference call — fresh process, fresh context window, provably no leakage. Nine run
   concurrently via `ThreadPoolExecutor`, keeping a full run under ~45 seconds.

2. **A leak bug that became a feature.** Our first grounded run showed incoherence *decreasing* (0.68×).
   The market-data block was showing all three ratios to every context, letting the model infer the
   constraint and enforce consistency it wouldn't otherwise have. We now slice the data block per-context.
   That bug is also the cleanest proof the phenomenon is real: give the model the whole picture and it
   becomes coherent; fragment it and it doesn't.

3. **No mocked-data fallback, anywhere.** If The Graph, 0G, or the quote is unavailable, the run fails
   visibly. A cached-price fallback would have been trivial and would have quietly invalidated every claim
   the demo makes.

**Same engine, two surfaces.** The dashboard and the MCP server call identical code paths, so
`coherence_check(pair, amount, reps, model)` returns the same verdict object a human sees — meaning any
MCP-capable agent can gate its own trades on it.

---

## Sponsor Fit

| Sponsor | Track | How it is load-bearing |
|---|---|---|
| **The Graph** | Best AI Tooling | Live Uniswap v3 subgraph defines the triangle constraint; shipped as a reusable MCP server ("guardrail or auditor layer", not a single app) |
| **Uniswap** | Best API Integration | The probe triangle wraps a real quoted swap; QuoterV2 produces the route the guard gates |
| **0G** | Best Infrastructure & Tooling | Every elicitation runs on 0G Compute; TEE attestation makes the incoherence proof unforgeable |

---

## Honest Assessment

**Established:**
- Models reliably place **3–9% of belief mass on logically impossible worlds** when contexts are separated
- Signalling stays negligible (≤0.02), so the measurement is clean
- Reproducible across 6+ independent runs

**Not established — and not claimed:**
- That live market data amplifies incoherence (1.32× observed, within noise)
- That poisoned oracle feeds are detected — one test of a crude +15pp spoof moved the metric the *wrong*
  direction (0.28×). Consistent lies get coherently believed. Subtle multi-leg attacks are untested.
- That incoherence predicts P&L

**The framing:** *coherent ≠ correct.* We detect self-contradiction, not wrongness. Like a compiler
type-check — passing doesn't prove your program correct, but failing proves it's broken. Cohesion is a
pre-trade sanity check on reasoning, never an alpha generator.

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
coherence/
  core.py          # LP incoherence measure + confidence intervals
  graph_client.py  # Uniswap v3 subgraph queries      <- The Graph
  uniswap.py       # QuoterV2 staticCall              <- Uniswap
  inference.py     # 0G Compute Router client         <- 0G
  triangle.py      # swap route -> propositions + per-context prompts
  server.py        # FastAPI, SSE stream, serves web/
  mcp_server.py    # MCP tool: coherence_check()
web/
  index.html       # single-page dashboard, no build step
experiments/       # pre-hackathon validation runs
specs/             # Spec Kit artifacts (spec, plan, tasks)
```

## Running It

```bash
cp .env.example .env    # GRAPH_API_KEY, ZG_API_KEY, ETH_RPC_URL
pip install -r requirements.txt
uvicorn coherence.server:app
```

Open `localhost:8000`, set up a swap, and run the check. Default is 3 reps per context (~45s); the slider
goes to 9 for higher confidence.

### Reproducing the original validation

```bash
cd experiments
python3 -m venv venv
./venv/bin/pip install scipy numpy
./venv/bin/python coherence_test.py 4    # baseline, 4 reps
./venv/bin/python coherence_ab.py 5      # A/B blind vs grounded, 5 reps
```

Uses the local `claude` CLI as the model under test. Each run ~5–10 minutes.

---

**Builder:** Slava Karkunov · karkunow@gmail.com
**Event:** ETHGlobal Lisbon 2026 (July 24–26)
