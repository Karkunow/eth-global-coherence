# Implementation Plan: Cohesion — Agent Coherence Guard

**Branch**: `001-agent-coherence-guard` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-agent-coherence-guard/spec.md`

## Summary

Measure whether an AI agent's beliefs about three correlated market variables can all be true at once, and use drift from that agent's own calibrated baseline to gate a trade.

The technical approach is a single decision engine with two thin interfaces. The engine builds a closed three-leg price cycle from live pool data, elicits the agent's forecasts in three process-isolated contexts, solves a small linear program to find how much belief mass cannot be placed in any possible world, and compares that reading against a stored per-configuration baseline using a two-sample test. A browser dashboard and a stdio MCP server both call the same engine and therefore return identical verdicts.

The load-bearing design decision is **baseline-relative gating**. Every model carries some baseline incoherence (validated at 3–9%), so an absolute test against the theoretical ideal would veto every agent on every run. Comparing against the agent's own calibrated normal is what makes the gate usable and what lets it detect silent degradation.

## Technical Context

**Language/Version**: Python 3.13.3 (single language across engine, server, and MCP; avoids a second runtime)

**Primary Dependencies**:
- `scipy` — `optimize.linprog` (incoherence LP), `stats.t` (confidence intervals), `stats.ttest_ind` (baseline drift test)
- `numpy` — sample aggregation
- `fastapi` + `uvicorn` — HTTP with Server-Sent Events for streamed partial results (FR-028)
- `httpx` — GraphQL queries to the live pool-data subgraph
- `web3` — on-chain quoter contract call for the executable trade quote
- `openai` — pointed at the 0G Compute Router (OpenAI-compatible), avoiding a TypeScript SDK and a second runtime
- `mcp` — stdio MCP server exposing the same engine

**Storage**: `baselines.json` — a single JSON file keyed by configuration hash. No database. Baselines are small (five scalars each), and file storage keeps the artifact reviewable and committable so a fresh clone reproduces a demo verdict.

**Testing**: `pytest` for the pure-math core (LP correctness, CI arithmetic, drift verdict boundaries) — these are deterministic and worth locking down. Integration behaviour is validated through the runnable scenarios in [quickstart.md](./quickstart.md) rather than mocked tests, because FR-004 forbids substituting synthetic data and mocking the live sources would test the mock.

**Target Platform**: Local developer machine. Browser dashboard served from the same process; MCP server over stdio for agent clients.

**Project Type**: Web service + static single-page frontend + MCP server, sharing one engine package.

**Performance Goals**: A gating check completes in under 45 seconds at reps=3 (SC-002). This requires the 9 elicitations (3 contexts × 3 reps) to run concurrently, not serially.

**Constraints**:
- No mocked, cached, or synthetic market data on any code path (FR-004) — there is deliberately no fallback to fail over to.
- Context isolation must be structural, not conventional (FR-005) — enforced by process/request separation rather than by prompt instructions.
- Per-context data slicing must withhold the third leg (FR-006) — a known regression risk; leaking it lets the agent infer the constraint and suppresses the signal.
- No monetary figure may be reported as an incoherence measure (FR-013).
- No transaction may be transmitted to a live network (FR-027).

**Scale/Scope**: Single operator, single concurrent run, one feature. Roughly 8 modules and one HTML page.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status: PASS (vacuous).**

`.specify/memory/constitution.md` is the unmodified Spec Kit template — every principle is still a `[PRINCIPLE_N_NAME]` placeholder. There are no ratified project principles to check this design against, so the gate cannot fail.

This is recorded honestly rather than by inventing principles to satisfy the gate. Two consequences worth naming:

1. **No TDD mandate applies.** The template's example constitution includes "Test-First (NON-NEGOTIABLE)", but it was never ratified here. This plan therefore adopts a narrower testing posture (deterministic core under unit test; integration validated through runnable scenarios) as an explicit engineering judgment, not as a constitutional exemption.
2. **If principles are later ratified**, this design must be re-checked against them. The most likely points of friction are the file-based storage and the absence of a mocked test path.

**Post-Phase-1 re-check**: PASS (unchanged — no principles exist to violate; Phase 1 introduced no new frameworks, no additional projects, and no persistence beyond the single JSON file already declared).

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-coherence-guard/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions and open items
├── data-model.md        # Phase 1 output — entities and state
├── quickstart.md        # Phase 1 output — runnable validation scenarios
├── contracts/           # Phase 1 output
│   ├── http-api.md      # Dashboard-facing HTTP + SSE contract
│   ├── mcp-tools.md     # Agent-facing MCP tool contract
│   └── verdict.md       # The shared verdict object both interfaces return
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
cohesion/
├── __init__.py
├── core.py              # Incoherence LP, confidence intervals — pure, deterministic
├── baseline.py          # Calibrate, load, and the drift verdict
├── triangle.py          # Probe construction, propositions, per-context prompts
├── graph_client.py      # Live pool prices (the constraint's data source)
├── uniswap.py           # Executable quote for the gated trade
├── inference.py         # Verifiable inference + attestation capture
├── orchestrator.py      # Runs a check or calibration end to end; emits progress events
├── server.py            # FastAPI app, SSE endpoints, serves web/
└── mcp_server.py        # stdio MCP server

web/
└── index.html           # Single page, no build step

tests/
└── unit/
    ├── test_core.py     # LP correctness, CI arithmetic, six-worlds enumeration
    └── test_baseline.py # Drift verdict boundaries, key derivation, no-baseline path

experiments/             # Pre-existing validation scripts (unchanged by this feature)
baselines.json           # Created at first calibration; committed for reproducibility
```

**Structure Decision**: Single Python package (`cohesion/`) with two entry points (`server.py`, `mcp_server.py`) over one shared engine (`orchestrator.py`). This is the structure that makes FR-030 — identical verdicts from both interfaces — true by construction rather than by discipline: both entry points call `orchestrator.run_check()` and neither contains decision logic of its own.

The layering is deliberate and one-directional:

- `core.py` and `triangle.py` are **pure** — no network, no clock, no I/O. This is what makes the mathematics unit-testable without touching a live source, and it is where the honesty constraints are enforced structurally (the LP simply has no dollar-denominated output to report, satisfying FR-013 by construction).
- `graph_client.py`, `uniswap.py`, and `inference.py` are the three **I/O boundaries**, one per external dependency. Each raises on unavailability and none has a fallback path — FR-004 is enforced by the absence of the code that would violate it.
- `orchestrator.py` composes them and is the only module that knows the full sequence.
- `server.py` and `mcp_server.py` are **transport only**.

`web/` is deliberately a single static file with no build step. A toolchain would cost setup time and add a failure mode during a live demo, and the page's needs (a form, a streamed list, a gauge, a verdict banner) do not warrant a framework.

## Complexity Tracking

> No Constitution Check violations to justify — the constitution defines no principles.

One design choice is worth recording anyway, since it will look like unnecessary complexity to a reviewer:

| Choice | Why needed | Simpler alternative rejected because |
|--------|-----------|-------------------------------------|
| Process-isolated elicitation (separate inference call per context, never a shared conversation) | FR-005 requires that no context can access another's answers. This is the entire validity basis of the measurement. | Instructing a single conversation to "answer independently" is unverifiable and was the source of the previously observed 0.68× leak. Isolation must be structural, or the measurement means nothing. |
