# ETHGlobal Lisbon 2026 — Project Ideas

Profile: math / physics / quantum computing / category theory background. Solo. ~24-30h coding time. AI agents must be core, not decorative.

---

## Idea 1: Contextuality Coherence Certificate — PURSUE ✅

### The problem
TEE-based attestation (0G Sealed Inference) proves an AI agent's answer is *authentic* — it really came from the claimed model, wasn't tampered with. But it says nothing about whether a **panel** of such agents' answers are mutually **coherent**, i.e. describe one possible world.

### The mechanism
Abramsky–Brandenburger sheaf-theoretic contextuality (the math behind Bell/Kochen–Specker non-locality in quantum foundations) gives a quantitative, LP-computable measure of exactly this: the **contextual fraction**.

1. Run K AI agents (each inside 0G Sealed Inference, for authenticity) over overlapping "contexts" — subsets of correlated questions (e.g. "will ETH>X?", "will ETH/BTC>Y?", "will pool imbalance exceed Z?").
2. Compute the contextual fraction via a small linear program (~20-50 lines, scipy.linprog): can the marginals glue into one joint distribution?
3. LP duality gives you a **Dutch book for free** — an explicit portfolio of bets, priced at the panel's own numbers, that loses money in *every possible world* if the panel is incoherent.
4. Ship as an SDK wrapping 0G Sealed Inference; index coherence certificates via The Graph (querying **live on-chain data as the panel's subject matter**, not just storing your own blobs); optionally attach an agent's coherence record to its ENS name.

### Demo wow moment
Two AI agent panels, both pass every pairwise consistency check a judge would think to run. Live: **"For Panel B, here's a portfolio of bets priced at their own numbers. In every possible world, it loses $137. Not usually — always."** Then show the number (0.41) and the topology (simplicial complex, violating context highlighted).

**Critical framing note:** Lead with the money (Dutch book), THEN the number, THEN the topology — in that order. Leading with "contextual fraction = 0.41" reads as math theater to a non-specialist judge.

### Target bounties
- **0G — Best Infrastructure & Tooling** ($4.5k) — primary target, explicitly wants novel primitives. (Best AI Product $6k as backup framing.)
- **The Graph — Best AI Tooling** ($5k) — MUST use live Graph data as the agents' subject matter (pool imbalances, real prices/volumes), not just store your own certificates. A subgraph of your own blobs does NOT qualify per Graph's stated criteria ("mocked or static data does not qualify").
- **ENS — Best Integration for AI Agents** ($1.5k) — STRETCH ONLY. Must be functional (agent resolves counterparty by ENS name, reads coherence record, refuses/down-weights before consuming), not cosmetic (just writing a score to a text record fails their stated criteria).

### Prior art (searched)
- **"Locally Coherent, Globally Incoherent" (arXiv 2605.30335, 2026)** — applies de Finetti's coherent polytope to multi-agent LLM systems, very close to this idea, different math framing (no sheaf language), earlier. Do NOT claim world-first on the core measurement. Your genuine differentiator: this detects impossibility with *zero disagreement* on any shared question — a categorically different failure than variance/disagreement scoring.
- **"Quantum-Like Contextuality in LLMs" (arXiv 2412.16806, 2025)** — sheaf contextuality already applied to LLMs (BERT), needed a signalling-corrected model because real language data signals.

### Known risks
1. **Signalling problem** (main technical landmine): real LLM panels violate the no-signalling condition. Fix: report both a signalling fraction AND contextual fraction, be upfront about it — costs ~30-45 min, converts weakness into evidence of rigor.
2. **Scope**: 3 sponsors + subgraph + ENS + TEE + visualizer ≈ 35-45h against a 24-30h budget. Must cut ENS to stretch-only.
3. **Constructed "Panel B" looks fake**: don't hand-build the incoherent panel. Use a genuine **3-cycle / Specker's triangle** setup — 3 correlated market props, 3 pairwise contexts — and let incoherence emerge naturally from real LLM calls (~1h of prompt iteration).

### First step (do this before writing any integration code)
**90 minutes:** Pick 3 correlated market propositions. Query real LLM panels on the 3 pairwise contexts. Check if the resulting empirical model is (a) near-non-signalling and (b) actually infeasible under the joint LP while passing all pairwise checks.
- If genuine incoherence emerges → build the rest, you have your demo.
- If not after ~2h → pivot framing from "we detect incoherent panels in the wild" to "we detect **collusion**: a compromised subset of agents can't fake a globally consistent world without coordinating across contexts they can't all see" — a legitimate, more crypto-native threat model where a constructed adversarial panel is the *correct* demo, not a cheat.

---

## Idea 4: Proof of Bounded Delegation — REFINE ⚠️ (fix before building)

### The problem / assumption challenged
World ID answers "human or bot." The claim: in an agentic economy, the actually load-bearing question is **"is this AI agent the authorized limb of exactly one human, and how much delegated authority does it have left?"** — a proof-of-bounded-delegation problem, not proof-of-personhood. World ID should be the *root* of trust, not the whole answer.

### The mechanism (as originally proposed — contains a flaw, see below)
Give the AI agent a Merkle tree of Winternitz one-time-signature (WOTS) leaves. Every action consumes one leaf irreversibly. Root minted by a World ID-verified human. Agent's ENS subname (`trader.slava.eth`) carries the tree root as a text record. Built entirely on native Hedera SDK (HTS + HCS + Schedule Service) — no Solidity.

### ⚠️ The central claim is FALSE as originally stated
Original pitch: "overspending isn't rejected, it's cryptographically **impossible**, nothing on-chain decides to block it."

**This is not true.** The agent holds all the WOTS private keys — nothing physically stops it from reusing a leaf's key material twice. What actually prevents reuse is **a verifier checking a used-leaf set** — that's a checked rule with exactly the state-management attack surface the pitch claims to eliminate. Also: WOTS bounds *action count*, not *value* — you still need a rule to bound spend amounts unless each leaf is pre-committed to a specific bounded action.

**Before writing any code, answer in one paragraph:** *"When the agent tries to consume leaf 3 a second time, what physically stops it, and who is trusted?"* If the answer contains "our verifier checks" — the impossibility framing must be deleted and replaced with the reframe below.

### The reframe that survives scrutiny (use this instead)
**Nugget:** Delegated authority should be a finite, pre-committed resource that composes **downward and can only shrink** — bounded by what a sub-agent structurally holds, not by rules that must compose correctly — with every action carrying **unforgeable, non-repudiable attribution even against a compromised relayer**.

Two genuinely true, genuinely differentiated properties:
- **(A) Unforgeable attribution against a compromised relayer** — every action's WOTS signature + HCS timestamp means even a malicious relayer/operator cannot fabricate or retroactively alter the log of what an agent did.
- **(B) Recursive sub-delegation that can only shrink** — a sub-agent's subtree size structurally bounds its authority; a sibling subtree is unreachable by construction (provable via the Merkle auth path), not by a rule that could have a bug. Budget is a *measure on the leaf set*; delegation is an *inclusion of subobjects*; conservation is structural, not enforced. Session keys/ERC-7715 handle this badly because sub-delegation there means writing more rules.

### Demo wow moment (revised)
Human roots a 64-leaf tree for `trader.slava.eth` via World ID. `trader` sub-delegates a 16-leaf subtree to `scout.trader.slava.eth`. Live: scout attempts a 17th spend AND attempts to reach into a sibling subtree — both fail, and you show the Merkle auth path proving there's structurally no path to the sibling. Then: the relayer tries to fabricate a spend on the agent's behalf and fails (no valid signature it could forge). Everything auditable from the ENS text record + HCS topic by any third party, no trusted component needed.

### Target bounties
- **Hedera — "No Solidity Allowed"** ($3k) — primary target; HCS + HTS alone satisfies "≥2 native services." Have a ready answer for "why not just use `AccountAllowanceApproveTransaction`?" (native Hedera allowance feature): *"That caps value; it doesn't tell you which agent did what, can't be sub-delegated without the owner online, and the operator's word is the only record. We give unforgeable attribution and conservative sub-delegation."*
- **World** ($15k, sub-track TBD — "coming soon" as of last check) — real IDKit + Developer Portal Simulator integration is feasible in ~2-3h. **Risk: check the moment World's track spec publishes — if it requires a Mini App (MiniKit, in-World-App), a plain web app scores poorly and you'd need ~3h extra to wrap it.**
- **ENS — Best Integration for AI Agents** ($1.5k) — use a subname service (Namestone/Durin-style) on testnet, ~1.5h. Follow ENSIP-25/26/27 conventions for agent identity — cheap extra credibility.

### Prior art (searched)
- **PayWord (Rivest–Shamir, 1996)** — hash-chain micropayments, same core "spend by revealing/consuming a bounded hash structure" idea.
- **Amazon patents (US10129034, US10218511, US10237249)** — signature delegation via revocable one-time-key subtrees, essentially the same mechanism already patented.
- Mechanism is not new; the **composition** (World ID root + ENS-published + Hedera-native + AI agent framing) is new packaging.
- **Timing bonus:** Ethereum's "Lean Ethereum" roadmap (published ~3 weeks before this hackathon) commits to leanXMSS hash-based validator signatures — hash-based signatures are current zeitgeist among exactly this judge pool, not stale PQ branding.

### Mandatory scope cuts for a solo 24-30h build
- Hypertree → flat Merkle tree, 64 leaves (hypertree buys nothing at demo scale, costs 3h).
- WOTS (not WOTS+) — skip bitmasks/PRF key gen. w=16, SHA-256, n=32, with checksum, ~120 lines TS, ~4h with tests. No mature JS/TS WOTS library exists — port from Go (`lentus/wotsp`, RFC 8391) or Python (`winternitz` on PyPI) reference implementations. Write the test-vector check FIRST.
- Drop Schedule Service to stretch-goal only.
- Drop "Tokenization on Hedera" as a target — poor fit, don't chase it.

### First step
**10 minutes:** Write the one-paragraph answer to "what physically stops leaf reuse, and who is trusted?" — this determines whether you're building the honest (attribution + conservative sub-delegation) version or the false (impossibility) version. Do this before any code.

---

## Idea 2: Natural-Gradient AMM Rebalancing — KILLED ❌

**Why:** Scooped almost verbatim by Matthew Willetts, "Riemannian Geometry of Optimal Rebalancing in Dynamic Weight AMMs" (arXiv:2603.05326, March 2026) — author works at QuantAMM.fi, a live protocol already shipping this. Paper includes the exact theorem, the exact metric, a real backtest, Monte Carlo validation, and an on-chain algorithm. The demo's own numbers (from the paper) show the effect is sub-percent and vanishes as O(Ω⁴/f³) at realistic rebalancing frequencies — the "wow" moment likely doesn't survive a different date range.

**Open pivot (untested, not evaluated):** Optimal transport over tick-space liquidity in concentrated-liquidity pools (CLMM) — Fisher-Rao metric is structurally blind to *how far* liquidity moves in tick-space, Wasserstein/optimal-transport isn't. No prior art found for this specific angle. Would need its own idea-critic pass before committing.

---

## Decision Summary

| | Idea 1: Contextuality Certificate | Idea 4: Proof of Bounded Delegation |
|---|---|---|
| Verdict | PURSUE | REFINE |
| Strength | Cleanest single visual "wow", bulletproof math once framed as Dutch-book, smallest integration surface | Best narrative timing (Lean Ethereum), most "uniquely yours", hits 2 Hedera sub-tracks at once |
| Risk | Empirical — does genuine panel incoherence actually emerge? | Broadest integration surface (3 SDKs); World's track spec not yet published; false claim must be fixed first |
| First step | 90 min: 3-cycle elicitation test with real LLM panels | 10 min: write the "what physically stops leaf reuse" paragraph |
| Est. build time | ~20-30h | ~24-31h, zero slack |

**Recommendation: Idea 1.** One open question (resolves in 90 min, has a clean fallback). Idea 4 depends on an unpublished World spec and touches more distinct SDKs.
