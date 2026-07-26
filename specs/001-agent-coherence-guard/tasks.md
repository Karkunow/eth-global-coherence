---

description: "Task list for Cohesion — Agent Coherence Guard"
---

# Tasks: Cohesion — Agent Coherence Guard

**Input**: Design documents from `/specs/001-agent-coherence-guard/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included, scoped exactly as plan.md's Technical Context specifies — `pytest` for the pure-math core only (`cohesion/core.py`, the drift-verdict boundaries in `cohesion/baseline.py`). No mocked integration tests: FR-004 forbids substituting synthetic data for the live sources, so mocking them would test the mock. Integration behaviour is validated through the runnable [quickstart.md](./quickstart.md) scenarios instead.

**Organization**: Tasks are grouped by user story (P1 calibrate, P2 advise on a trade, P3 MCP) per [spec.md](./spec.md), preceded by Setup and Foundational phases shared by all three.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact, matching the structure in [plan.md](./plan.md)'s Project Structure section

---

## Phase 1: Setup

**Purpose**: Project initialization

- [ ] T001 Create `cohesion/` package (`__init__.py` plus empty stub files `core.py`, `baseline.py`, `triangle.py`, `graph_client.py`, `uniswap.py`, `inference.py`, `orchestrator.py`, `server.py`, `mcp_server.py`), `web/index.html` placeholder, and `tests/unit/` directory, per plan.md's Project Structure
- [ ] T002 Create `requirements.txt` (or `pyproject.toml`) with `scipy`, `numpy`, `fastapi`, `uvicorn`, `httpx`, `web3`, `openai`, `mcp`, `pytest`, matching plan.md's Primary Dependencies
- [ ] T003 [P] Implement `cohesion/config.py`: load and validate all required `.env` vars (`GRAPH_API_KEY`, `GRAPH_SUBGRAPH_ID`, `GRAPH_GATEWAY`, `UNISWAP_API_KEY`, `UNISWAP_API_BASE`, `ETH_RPC_URL`, `UNISWAP_QUOTER_V2`, `ZG_API_KEY`, `ZG_API_BASE`, `ZG_MODEL`, `COHESION_DEFAULT_REPS`, `COHESION_CALIBRATE_REPS`, `COHESION_CONFIDENCE`, `COHESION_PRODUCT_TOLERANCE`); raise loudly on any missing required value rather than defaulting silently, matching the no-substitution posture of FR-004

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared engine primitives every user story elicits, measures, or reads through. No user story can be implemented until this phase is complete.

**⚠️ CRITICAL**: Do not start Phase 3+ until this phase is done.

- [ ] T004 Implement the six-worlds enumeration, `FORBIDDEN = {(1,1,1), (0,0,0)}`, and `incoherence_lp()` (scipy `optimize.linprog`, maximizes assignable mass over the 6 possible worlds against the observed pairwise marginals) in `cohesion/core.py`, per data-model.md's "The six possible worlds" section
- [ ] T005 Implement `confidence_interval()` in `cohesion/core.py`: per-context standard error of the disagreement-mass estimate, combined across the three independent contexts (variances add), returning the 95% t-interval via `scipy.stats.t.ppf(0.975, reps-1)` — return null bounds when reps < 3 (FR-011, FR-012)
- [ ] T006 Implement `analyse()` in `cohesion/core.py`: assembles a `CoherenceReading` (`incoherence`, `disagreement_sum`, `std_error`, `ci_low`, `ci_high`, `reps`, `signalling`, `samples_used`, `samples_discarded`) from a set of `ElicitationSample`s — no monetary field anywhere in this entity, by construction (FR-013)
- [ ] T007 `tests/unit/test_core.py`: six-worlds enumeration yields exactly 6 possible worlds with `(1,1,1)`/`(0,0,0)` excluded; every possible world has exactly 2 disagreements; uniform distribution over the 6 worlds gives `disagreement_sum == 2.000` and `incoherence == 0.0`; a distribution placing mass on a forbidden world gives `incoherence > 0`; t-critical at reps=3 is 4.30 (not ~2.0); reps < 3 returns null for `std_error`/`ci_low`/`ci_high` — matches quickstart Scenario 0
- [ ] T008 [P] Implement `cohesion/triangle.py`: third-asset selection from the fixed liquid set by highest TVL (FR-001), the three propositions, and the per-context prompt/data-block builder that shows each `ContextSlice` only its own two legs' prices — data block MUST NOT contain the third leg's price, ratio, or any derivable value (FR-005, FR-006; this is the correctness-critical leak-discipline invariant from data-model.md's `ContextSlice` entity)
- [ ] T009 [P] Implement `cohesion/graph_client.py`: query the Uniswap v3 subgraph for the three pools (`token0Price`, `token1Price`, `feeTier`, `liquidity`, `totalValueLockedUSD`), verify `abs(product - 1.0) <= 0.01` and abort with a clear explanation if not (FR-003), raise `DATA_UNAVAILABLE` with no cached/synthetic fallback on any failure (FR-002, FR-004)
- [ ] T010 [P] Implement `cohesion/inference.py`: OpenAI-compatible client against the 0G Compute Router (`ZG_API_BASE`), sequential calls with exponential backoff (research D8 — 5-way concurrency triggers 503, ~1 req/s serial triggers 429), model-family-specific request shaping per research D10's mainnet findings (Claude models need `/messages` + `x-api-key` + `anthropic-version`, not `/chat/completions`; `deepseek-*` needs `enable_thinking: false` to avoid burning `max_tokens` on hidden reasoning; always send a browser-like `User-Agent` to avoid the Cloudflare 1010 block), attestation capture (`model_reported`, `response_id`, `provider_address`, `verifiability`, `signature?` — label as *reported*, never *verified*, absent a signature per research O1), and discard-not-repair of unparseable responses (FR-008, FR-009)
- [ ] T011 Implement `cohesion/orchestrator.py`'s shared progress-event scaffolding: an event-emitting shape (`probe`, `quote`, `baseline`, `sample`, `reading`, `verdict`, `done`) that both `run_calibration()` (Phase 3) and `run_check()` (Phase 4) will populate, emitting `sample` events as each elicitation returns rather than batched at the end (FR-028) — depends on T004–T010

**Checkpoint**: Foundation ready — core math, probe construction, live data, and inference are all in place. User story work can begin.

---

## Phase 3: User Story 1 - Calibrate an agent's health baseline (Priority: P1) 🎯 MVP

**Goal**: An operator picks an agent (model + system prompt) and a pair, runs calibration (9–15 reps × 3 contexts), and gets a stored, published health figure (e.g. "4.5% incoherence").

**Independent Test**: Select an agent and pair, run calibration to completion, and confirm a stored health profile exists with an average incoherence, a spread, and a sample count — and that re-running calibration on the same configuration produces a comparable figure.

### Implementation for User Story 1

- [ ] T012 [P] [US1] Implement baseline key derivation in `cohesion/baseline.py`: `key = sha256(model ‖ prompt ‖ data_source ‖ probe_descriptor)`, such that changing any one of these four changes the key (FR-015)
- [ ] T013 [US1] Implement `store_baseline()` / `load_baseline()` in `cohesion/baseline.py` against `baselines.json`: atomic write (write-temp-then-rename) so an interrupted run leaves the file completely unchanged (FR-014, FR-017); depends on T012
- [ ] T014 [US1] `tests/unit/test_baseline.py`: key changes when model, prompt, data source, or probe changes; a simulated partial write leaves `baselines.json` untouched — matches quickstart Scenario 5's two negative checks; depends on T013
- [ ] T015 [US1] Implement `orchestrator.run_calibration()` in `cohesion/orchestrator.py`: `IDLE → FETCHING_POOLS → [product check] → ELICITING (9–15 reps × 3 contexts) → COMPUTING → CONFIRMING_OVERWRITE? → STORED`, any failure returns to `IDLE` without writing (FR-017); depends on T011, T013
- [ ] T016 [US1] Implement `POST /api/calibrate` SSE endpoint in `cohesion/server.py` per contracts/http-api.md: validates `reps` is 9–15 (FR-016), emits `exists` when a baseline is already present and `overwrite=false` without writing (FR-018), emits `stored` on completion; depends on T015
- [ ] T017 [US1] Implement `GET /api/baselines` endpoint in `cohesion/server.py` (lists stored baselines per contracts/http-api.md); depends on T016
- [ ] T018 [US1] Build the Calibrate section of `web/index.html`: agent (model + system prompt) and pair form, reps slider (9–15), streamed sample list as each context's reps land, published health-% result, and the overwrite-confirmation prompt (FR-018); depends on T016, T017

**Checkpoint**: User Story 1 is fully functional and independently testable — an operator can calibrate an agent and see a published health score.

---

## Phase 4: User Story 2 - Advise on a trade against the baseline (Priority: P2)

**Goal**: A user sets up an ordinary trade, gets a real quote, and the guard advises (never blocks) based on a fast check compared against the calibrated baseline — PASS unlocks freely, VETO/NO_BASELINE/INSUFFICIENT_SAMPLES require explicit acknowledgement before proceeding.

**Independent Test**: Calibrate an agent (US1), then set up a trade and run the guard, confirming a within-baseline reading lets the user proceed unimpeded while a significantly-worse reading demands explicit acknowledgement first — each verdict displaying its confidence level and repetition count.

### Implementation for User Story 2

- [ ] T019 [P] [US2] Implement `cohesion/uniswap.py`: Trading API `POST /v1/quote` as the primary path (unlocks the $7k track qualification), QuoterV2 `staticCall` as fallback (non-`view`, must be a static call — see research D5), returning `amount_out`, `fee_tier`, `gas_estimate`, `pool_address` (FR-026)
- [ ] T020 [P] [US2] Implement the drift-verdict decision rule in `cohesion/baseline.py`: one-sided Welch's t-test (`scipy.stats.ttest_ind`, `equal_var=False`) of the current reading against the stored baseline at the configured confidence — `NO_BASELINE` if no baseline for the config key, `INSUFFICIENT_SAMPLES` if reps < 3, `VETO` only if significantly worse (FR-019, FR-020), `PASS` + drift notice if significantly better (FR-023), `PASS` otherwise; sets `requires_acknowledgement` true for every outcome except `PASS` (FR-021, FR-025)
- [ ] T021 [US2] `tests/unit/test_baseline.py`: no baseline → `NO_BASELINE`; reps < 3 → `INSUFFICIENT_SAMPLES`; significantly-worse reading → `VETO`; significantly-better reading → `PASS` with a note; within-baseline reading → `PASS`; `requires_acknowledgement` is true iff outcome ≠ `PASS`; depends on T020
- [ ] T022 [US2] Implement `orchestrator.run_check()` in `cohesion/orchestrator.py`: `IDLE → QUOTING → FETCHING_POOLS → [product check] → ELICITING (3 reps × 3 contexts) → COMPUTING → COMPARING → VERDICT`, streaming per-sample attestation stamps as they land (FR-028); depends on T011, T019, T020
- [ ] T023 [US2] Implement `GET /api/pools`, `GET /api/quote`, and `GET /api/check` (SSE) in `cohesion/server.py` per contracts/http-api.md's full event sequence (`probe → quote → baseline → sample* → reading → verdict → done`, plus `error` events for `PROBE_INVALID`/`DATA_UNAVAILABLE`/`QUOTE_UNAVAILABLE`); depends on T022
- [ ] T024 [US2] Build the trade + gate section of `web/index.html`: swap form, live quote, an Execute button that starts disabled/labelled "awaiting coherence check" (FR-024), streamed sample list with attestation stamps, a gauge showing the 2.000 mark + baseline band + this run's CI, and a verdict banner — PASS unlocks Execute with no friction, VETO/NO_BASELINE/INSUFFICIENT_SAMPLES require an explicit deliberate click-through acknowledging the warning (worded per FR-025a: drift means reasoning changed, NOT that the trade is unprofitable) before Execute unlocks, and the action is never permanently disabled (FR-025); depends on T023

**Checkpoint**: User Stories 1 and 2 both work — the full advisory-gated trade demo is functional.

---

## Phase 5: User Story 3 - Machine-callable verdict for other agents (Priority: P3)

**Goal**: A calling agent gets a structured, programmatically-actionable verdict over MCP, identical to what the dashboard reports for the same configuration.

**Independent Test**: Have a separate agent request a check for a pair and confirm it receives a machine-readable verdict with all stated fields, matching what the human-facing flow reports for the same configuration.

### Implementation for User Story 3

- [ ] T025 [P] [US3] Implement the `coherence_check` tool in `cohesion/mcp_server.py` per contracts/mcp-tools.md, wrapping `orchestrator.run_check()` directly — no new decision logic, so FR-030 (identical verdicts) holds by construction; depends on T022
- [ ] T026 [US3] Implement `coherence_calibrate` and `coherence_baselines` tools in `cohesion/mcp_server.py`, wrapping `orchestrator.run_calibration()` and the baseline-listing function respectively; depends on T025, T015
- [ ] T027 [US3] Register the MCP server, run the same pair/model/reps through both the dashboard and MCP, and confirm `outcome`, `incoherence`, and `disagreement_sum` match exactly (FR-030) — quickstart Scenario 8; depends on T026, T024

**Checkpoint**: All three user stories are independently functional. This is also the P3 demo beat: an agent checks itself via MCP and abandons a swap on VETO with no human intervening.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation and submission readiness across all three stories.

- [ ] T028 Run quickstart.md Scenarios 0–8 end to end against the real, live stack; fix any regressions found before moving on
- [ ] T029 [P] Write `FEEDBACK.md` and submit the Uniswap Developer Feedback Form linking to it — hard qualification requirement for the $7k track (research O4)
- [ ] T030 Run the two greps from quickstart's Final Gate table (`dutch|guaranteed loss|per \$100` in `cohesion/ web/` — expect no hits, FR-013; `mock|fallback|cached|sample_data` in `cohesion/` — expect no hits on data paths, FR-004) and fix any hits
- [ ] T031 [P] Update root `README.md` with an architecture diagram and explicit pointers to the lines implementing each sponsor integration (0G, The Graph, Uniswap all ask for this)
- [ ] T032 Commit `baselines.json` after a real calibration run so a fresh clone reproduces a demo verdict without recalibrating

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational; its independent test additionally assumes a baseline already exists (i.e. US1 has been run at least once), per spec.md's stated P1→P2 dependency
- **User Story 3 (Phase 5)**: Depends on Foundational, and directly wraps `orchestrator.run_check()`/`run_calibration()` from US1/US2 rather than adding new logic
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- `core.py` tasks (T004–T006) are sequential — same file
- `baseline.py` tasks are sequential within each story (T012→T013 in US1; T020 extends the same file in US2) but independent across files from `uniswap.py` (T019)
- `server.py` endpoint tasks are sequential within each story — same file
- Frontend (`web/index.html`) tasks depend on their story's endpoints being implemented first

### Parallel Opportunities

- Foundational: T008 (`triangle.py`), T009 (`graph_client.py`), and T010 (`inference.py`) are independent files and can run in parallel once T004–T007 (`core.py` + its test) are underway
- US1: T012 (`baseline.py` key derivation) has no dependency and can start as soon as Foundational is done
- US2: T019 (`uniswap.py`) and T020 (`baseline.py` drift verdict) touch different files and can run in parallel
- US3: T025 can start as soon as T022 (US2's `run_check()`) is done, without waiting on the rest of US2's server/UI tasks
- T029 (`FEEDBACK.md`) and T031 (`README.md`) are independent files and can run in parallel with each other and with T028/T030

---

## Parallel Example: Foundational Phase

```bash
# After T004-T007 (core.py + its test) are underway:
Task: "Implement cohesion/triangle.py per T008"
Task: "Implement cohesion/graph_client.py per T009"
Task: "Implement cohesion/inference.py per T010"
```

## Parallel Example: User Story 2

```bash
Task: "Implement cohesion/uniswap.py per T019"
Task: "Implement the drift-verdict decision rule in cohesion/baseline.py per T020"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational)
2. Complete Phase 3 (User Story 1)
3. **STOP and VALIDATE**: run quickstart Scenarios 0–1 and the calibration half of Scenario 5 independently
4. This alone is a demoable deliverable — a published, reproducible agent health score

### Incremental Delivery

1. Setup + Foundational → engine primitives ready
2. Add User Story 1 → validate independently → MVP demoable
3. Add User Story 2 → validate independently → full advisory-gated trade demo
4. Add User Story 3 → validate independently → MCP-callable, agent-vetoes-itself demo beat
5. Polish → submission-ready

---

## Notes

- No tasks in this list are marked `[P]` across the *same* file — only across independent files, per the Task Generation Rules
- `tests/unit/` tasks cover only the pure-math core and the drift-verdict boundaries, matching plan.md's explicit testing posture — do not add mocked integration tests against `graph_client.py`, `uniswap.py`, or `inference.py` (FR-004 forbids the fallback path that mocking would require)
- Commit after each task or logical group, per the project's incremental-commit convention
- Stop at any checkpoint to validate a story independently before continuing

---

## Phase 7: Degraded-Mode Demo Toggle (post-launch stretch)

**Added lightweight, without a full spec/plan cycle** — this is an operator/demo affordance within
User Story 2's already-speced scope (advise on a trade against the baseline), not a new capability, and the
underlying mechanism is already validated live (research.md D11, attempt 3: `VETO` at `p=4.98e-6`). A full
`speckit-specify` → `plan` → `tasks` cycle would be disproportionate ceremony for a small, well-understood
addition — tracked here instead.

**Non-negotiable constraint carried over from FR-004**: this must never be reachable from, or confusable
with, the real advisory-gate path. Separate function, separate endpoint, unmissable labeling — not a hidden
flag on `run_check()`/`GET /api/check`, so the real path stays textually untouched and every existing
grep/audit against it keeps passing.

- [X] T033 [P] Implement `orchestrator.run_check_degraded_demo()` in `cohesion/orchestrator.py`: mirrors `run_check()`'s event sequence but overrides the `(A,B)` and `(A,C)` context data blocks with the validated contradictory-claim injection on proposition A (research D11 attempt 3), leaving `(B,C)` and all live pool/quote data untouched. Emits a `demo_notice` event before `probe` stating plainly that context data is synthetically injected for demonstration. A clearly separate code path from `run_check()`, never called by it.
- [X] T034 [US2-adjacent] Implement `GET /api/check-degraded-demo` (SSE) in `cohesion/server.py`, wrapping T033 — distinct route from `/api/check`, same error-code mapping.
- [X] T035 [US2-adjacent] Add a clearly-labeled "Demo: synthetic contradiction (for demonstration only)" control to `web/index.html`'s trade/gate section, rendering a persistent orange/red banner for the duration of that run distinguishing it from a real check, wired to T034 instead of `/api/check`.
- [X] T036 Manual verification: run the demo toggle end to end, confirm it reproduces `VETO` live, confirm the real "Run coherence check" path is completely unaffected (same PASS behavior as before this phase).
