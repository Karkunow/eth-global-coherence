# Coherence Guard — Design Discussion Summary

*ETHGlobal Lisbon 2026 · captured 2026-07-25 · distills the pre-build Q&A that shaped the final plan*

---

## 1. Why 0G?

Two load-bearing reasons:

1. **Trust:** 0G's TEE attestation proves the forecasts really came from the stated model, unaltered.
   Without it, judges (or counterparties) must take our word that the incoherent answers weren't fabricated.
   With it, the incoherence proof is **unforgeable**.
2. **Prize fit:** 0G's Infrastructure & Tooling track ($4.5k) literally lists *"verification, guardrail, or
   auditor layer for on-chain agent actions"* as a wanted example — our project verbatim.

**One-line pitch:** *Attestation proves who spoke. We prove what they said is even possible.*

Practical note: 0G requires ~4 0G tokens minimum (3 ledger + 1 per provider) — verified to be a
contract-level requirement, identical on testnet, vs. a 0.1 0G/day faucet. Hence: buy ~$10–20 on mainnet.
Models on 0G Compute are discovered at runtime (`listService()`); names seen in 0G materials:
Llama-3.3-70B-Instruct, DeepSeek-R1-70B, Gemma 3 27B (~6 chat models on the Router).

---

## 2. What coherence measurement actually is

- **Core thesis:** coherence ≠ correctness. Coherence is a **necessary condition** for a model to be usable
  — a health check on the reasoning machinery itself. A coherent agent can still be wrong; an incoherent one
  is *provably broken*: its own stated probabilities imply guaranteed loss in every possible world.
- **Analogy:** a compiler type-check. Passing doesn't prove the program correct; failing proves it's garbage
  before you ship it. Cheap, needs no ground truth, verifiable by math alone.
- **How we prove it:** (1) ask the agent in three isolated contexts; (2) LP checks whether the three answers
  can be marginals of any single joint distribution; (3) if not, construct the Dutch book — a portfolio
  priced at the agent's own numbers that loses in all 6 possible worlds.
- **Why the value is real despite no outcome-correlation evidence:** it detects **malfunction, not
  misfortune** — a cheap negative filter, like a smoke detector. Veto/flag on incoherence; never conclude
  "coherent, therefore safe."
- The metric can't be gamed by lazy hedging: uniform 50/50-independent answers give a disagreement sum of
  1.5 — strongly *incoherent*. Scoring well requires actually internalizing the constraint structure.

### Model comparison (discussed, kept as stretch goal)
Comparing incoherence across 0G-hosted models is nearly free (same pipeline, different model param) and
makes a good leaderboard moment — but must be framed as **reasoning-hygiene ranking, not decision-quality
ranking**. High incoherence disqualifies; low incoherence is necessary, not sufficient.

---

## 3. Productization: coherence as a guardrail

Three product shapes, in order of concreteness:

1. **Pre-execution hook (the real product):** middleware in an agent framework's tool-call pipeline —
   before `execute_swap` / `place_order` / `approve_loan` goes through, the guard elicits beliefs, runs the
   LP, returns pass/veto/flag.
2. **Coherence certificate (crypto-native):** attested responses + LP verdict, bundled and signed.
   Counterparties/vaults/DAOs require a fresh certificate before accepting an agent's transaction — a
   composable trust primitive. 0G attestation is what makes the certificate worth anything to a third party.
3. **Fleet monitoring (SaaS):** scheduled checks across deployed agents; alert when incoherence drifts
   (after model updates, feed changes). "Datadog for agent reasoning quality."

### Execution cadence — NOT before every operation
- Each check ≈ 9+ inference calls, ~35–45 s. Per-trade gating of high-frequency agents is a non-starter, and
  conceptually overkill: the check probes the *model+context's reasoning integrity*, which is stable
  minute-to-minute.
- **Risk-tiered policy:** always before large/irreversible operations; on change (model swap, prompt update,
  new data feed, regime shift); periodic heartbeat with certificate TTL (like TLS certs / oracle staleness).
- **Pitch line:** *per-trade for whales, per-hour for fleets, always on change.*

---

## 4. What breaks coherence (re-check triggers)

Mechanistically plausible triggers; only the baseline phenomenon is experimentally validated.

- **Model swap:** coherence is a property of a *specific* model's calibration, not of "AI." A new model —
  or a silent provider-side weight update under the same name — resets everything known about coherence.
- **Prompt update:** the system prompt (the hidden developer-set instruction block defining role/style/rules)
  is effectively part of the forecaster. Changing it shifts each context's answers *independently* — nothing
  keeps those shifts mutually consistent (e.g. "be decisive, avoid hedging" pushes answers away from any
  gluable joint).
- **New data-feed source:** (a) format/units drift — inverted ratios, stale legs — feeds the contexts
  mutually inconsistent premises, injecting the feed's incoherence into the measurement; (b) grounding
  sensitivity is experimentally real (0.68x leaked → 1.32x fixed), direction inconclusive.
- **Market regime change (hypothesis, untested):** calm markets let the model lean on jointly-memorized
  priors; a volatility spike forces live per-context reasoning, where fragmentation appears. Example: a USDC
  depeg scare makes "WETH/USDC rises" carry contradictory hidden assumptions across contexts.

### Security events
- **Prompt injection:** poison lands in *one* context's input, not all three symmetrically — asymmetric
  belief shift is exactly the signature the cross-context check is built to catch. Plausible, untested.
- **Oracle/feed manipulation:** ⚠️ our one test (+15pp spoof) moved incoherence **down** (0.28x) — the model
  confidently believed the big lie instead of fragmenting. Hypothesis: only subtle multi-leg manipulation
  surfaces as incoherence. **Future work, never a claim.**
- **Model supply-chain compromise:** attestation is the primary defense; coherence adds an unproven
  *behavioral fingerprint* layer.
- **Hard limitation (say it before judges ask):** a *uniformly* biased agent passes — coherence detects
  **fragmented** compromise, not **uniform** compromise. Security analog of "coherent ≠ correct."

---

## 5. Why The Graph?

- **Technically:** the Uniswap v3 subgraph is the live data source that *defines the triangle* — pool
  prices, 24h changes, the per-context data slices the agent reasons over. No live data → no propositions.
  Mocked/static data explicitly disqualifies from their tracks.
- **Strategically:** the AI Tooling track ($5k) asks for reusable agent tooling — *"guardrail or auditor"*
  MCP servers — which is literally what we ship.

---

## 6. Why Uniswap — and the swap-guard reframing (key decision)

- **Original framing:** quote a 3-leg loop WETH→USDC→WBTC→WETH via QuoterV2 and veto it. Weakness: a 1:1
  round-trip is nobody's real trade (absent mispricing it's a wash). Triangular arbitrage itself is fully
  commoditized (open-source bots, MEV searchers, EigenPhi analytics) — zero novelty there, and we must not
  be mistaken for an arb detector.
- **Resolution (adopted):** the triangle is **not the trade — it's the probe built around a real trade.**
  - User (or agent) sets up an **ordinary swap** X→Y (default WETH→USDC) with a real Uniswap quote.
  - The guard **auto-constructs a probe triangle** containing that pair (third asset = highest-TVL of
    WBTC/USDT/DAI), elicits beliefs, runs the check.
  - The verdict **gates the Execute button**: pass → unlocked; veto → locked, Dutch book shown. No on-chain
    send — the gate itself is the demo.
  - Second demo beat: **Claude Code with Uniswap's own MCP tooling (github.com/Uniswap/uniswap-ai) + our
    `coherence_check` MCP**, vetoing its own swap mid-conversation — the strongest evidence of reusability
    for The Graph's AI Tooling track.
- **Judge answer for "who trades a 1:1 loop?":** nobody — it's instrumentation; the smallest structure where
  belief consistency is enforceable by arithmetic (reflex-hammer analogy).

### Multiple triangles?
In theory, yes — better coverage of belief space, shared edges add stronger joint constraints (the
sheaf-theoretic generalization), aggregation gives a robust health score. In the demo, no — cost is linear
(9+ calls per triangle) and one triangle → one gauge → one veto is the 60-second story. The MCP interface
already takes the pair as a parameter, so multi-triangle sweeps are a caller-side loop later. Roadmap line
in the pitch.

---

## 7. Demo design: showing VETO vs PASS (discussion in progress)

**Test protocol today** (`coherence_ab.py`): 3 fresh `claude -p` processes, one per proposition pair
(A,B)/(B,C)/(A,C); each conversation sees only its two propositions + leak-fixed data slice, returns a
4-outcome joint as JSON; averages over reps feed the LP.

**Why "PASS in one window" was rejected:** eliciting all three legs in a single conversation changes the
*protocol*, not the agent — coherence becomes guaranteed by construction (any single distribution glues with
itself). It shows "protocol B passes," not "an agent passes the actual guard." Keep it only as a diagnostic
exhibit: proof the incoherence comes from fragmentation, not from unanswerable questions.

**Honest PASS options (same 3-probe protocol, different agent under test):**
1. **Different model** — probe 2–3 0G-hosted models; one may land within the CI of 2.000. Doubles as the
   model-comparison moment.
2. **Disciplined system prompt** — an agent instructed to keep probabilities jointly consistent vs. a naive
   one; story: "the guard certifies well-built agents, catches sloppy ones."
3. **Low scrutiny** — at reps=3 the t-interval is wide (4.30×SE); a clean run may honestly not exclude
   2.000. Zero work, weakest story (and same-agent pass-at-3/fail-at-9 looks self-contradictory on stage).

All untested → tonight's validation run searches for a passing configuration. Fallback if nothing passes:
"no current model survives fragmentation unaided" as a pitch line + clean-VETO vs attack-VETO contrast.

**Compromise-the-model attack (the hard-VETO wow):** crude uniform spoofing fails (validated: consistent
lies get coherently believed, 0.28x). The working design is **asymmetric compromise** — two narrative skins
of the same mechanism:
- *Split-brain feed poisoning:* attacker serves different WETH data per context (malicious oracle / MITM).
- *Backdoored agent:* sabotaged system prompt that fires only in some contexts ("be bullish on ETH/USDC").
Either way, contradictory premises about the same leg cannot glue → LP flags, signalling spikes, huge Dutch
book. Mechanically near-certain but must be validated once before demoing.

**Candidate demo ladder (pending tonight's validation):** good agent → PASS · sloppy agent → VETO ·
attacked agent → hard VETO — all under the identical three-probe protocol.

---

## 8. Overall viability verdict

- **Validated:** the phenomenon (3–9% mass on impossible worlds, 6+ runs), the Dutch book ($6–17/$100),
  negligible signalling (≤0.02).
- **Not validated — never claim:** live data amplifies incoherence (1.32x, within noise); poisoned feeds are
  detected (opposite result); incoherence predicts P&L.
- **Statistical honesty built in:** veto requires the 95% t-interval (df = reps−1) to exclude 2.000;
  reps ≥ 3 minimum for any verdict; "no significant violation" is a first-class honest outcome.
- **Pool-price caveat:** the product identity is exact for cross-rates from one source, approximate for
  three independent AMM pools (held ≈1 by arbitrage within the fee band); the 1% product check at run start
  certifies the triangle is tight, and typical 24h moves dwarf the band.
- **Honest pitch:** *coherent ≠ correct — we detect self-contradiction, not wrongness.* A pre-trade sanity
  check on reasoning; a smoke detector, not an alpha generator.
