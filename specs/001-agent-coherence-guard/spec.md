# Feature Specification: Cohesion — Agent Coherence Guard

**Feature Branch**: `001-agent-coherence-guard`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "Build Cohesion, a reasoning health check for AI agents that gates trades before capital moves. It measures whether an agent's beliefs about correlated market variables could all be true at once... the pass/fail decision is made against that agent's own calibrated baseline, not against the theoretical ideal — the guard fires on drift, which is what makes it usable as a gate and what lets it detect silent model degradation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Calibrate an agent's health baseline (Priority: P1)

An operator responsible for an autonomous trading agent wants to know how internally consistent that agent's reasoning normally is, so they have a reference point for detecting later degradation.

The operator selects an agent (identified by its underlying model and its system prompt) and a trading pair. The system constructs a probe — a closed three-leg cycle built around that pair from live market data — and asks the agent to forecast each leg's direction in three separate, isolated conversations, repeating each one many times. The system measures how much of the agent's belief mass falls on outcomes that cannot logically occur, and records the average, the spread, and how many samples were taken. The operator sees a single health figure, for example "this agent runs at 4.5% incoherence."

**Why this priority**: Every later capability depends on a stored baseline — without one, no verdict can be rendered at all. It is also independently valuable on its own: a published, reproducible health score for a given agent configuration is a deliverable in its own right, useful for comparing agents or tracking one agent over time, with no gating involved.

**Independent Test**: Can be fully tested by selecting an agent and a pair, running calibration to completion, and confirming that a stored health profile exists containing an average incoherence figure, a measure of spread, and a sample count — and that re-running calibration on the same configuration produces a comparable figure.

**Acceptance Scenarios**:

1. **Given** an operator has chosen an agent and a trading pair with no prior baseline, **When** they run calibration, **Then** the system elicits forecasts across three isolated contexts with at least nine repetitions each and stores a health profile containing the average incoherence, its spread, and the sample count.
2. **Given** calibration has completed, **When** the operator views the result, **Then** they see the agent's normal incoherence expressed as a percentage.
3. **Given** a health profile already exists for an agent configuration, **When** calibration is run again for that same configuration, **Then** the operator is informed a baseline already exists and can choose to replace it.
4. **Given** the live market data source is unreachable, **When** calibration is attempted, **Then** the system reports the failure and stores no baseline, rather than proceeding with substituted or remembered data.

---

### User Story 2 - Advise on a trade against the baseline (Priority: P2)

A user is about to commit capital through an autonomous agent and wants assurance the agent's reasoning has not degraded since it was last known good.

The user sets up an ordinary trade — a pair and an amount — and receives a real quote. Before committing, the guard runs a fast check, showing each isolated forecast as it arrives together with proof of which model produced it, then compares the result against the stored baseline.

The system **advises rather than blocks**. If the reading is consistent with the agent's normal behaviour, the user proceeds without friction. If it is significantly worse, the user sees a prominent warning explaining that the agent's reasoning has drifted, and must acknowledge it deliberately before continuing — but the decision remains theirs. If no baseline exists, no verdict is offered and the user is directed to calibrate first.

Advising rather than blocking is deliberate. Coherence is a necessary but not sufficient condition for sound reasoning: an incoherent agent is provably self-contradictory, but that does not establish the trade is unprofitable. Blocking would assert more than the measurement supports.

**Why this priority**: This is the capability that makes the health score actionable — it puts the measurement in front of someone at the moment it matters. It depends on P1 and is the primary demonstration of value.

**Independent Test**: Can be fully tested by calibrating an agent, then setting up a trade and running the guard, and confirming that a within-baseline reading lets the user proceed unimpeded while a significantly-worse reading demands an explicit acknowledgement first — with each verdict displaying its confidence level and how many repetitions it was based on.

**Acceptance Scenarios**:

1. **Given** a stored baseline exists and the user has set up a trade, **When** the commit action is first presented, **Then** it is labelled as awaiting a coherence check and no verdict is yet displayed.
2. **Given** a check has run and the reading is statistically consistent with the baseline, **When** the verdict is shown, **Then** it reads as a pass, states its confidence level and repetition count, and the user may proceed without further friction.
3. **Given** a check has run and the reading is significantly worse than the baseline, **When** the verdict is shown, **Then** it reads as a veto with a prominent warning, states its confidence level and repetition count, and the user must explicitly acknowledge the warning before proceeding.
4. **Given** a veto warning is displayed, **When** the user reads it, **Then** it states that drift indicates the agent's reasoning has changed and does NOT claim the trade is unprofitable.
5. **Given** no baseline exists for the selected agent configuration, **When** the user attempts a check, **Then** the system renders neither a pass nor a veto, and instead directs the user to run calibration first.
6. **Given** a check is running, **When** each isolated forecast returns, **Then** the user sees it appear along with evidence of which model produced it, rather than waiting for a single result at the end.
7. **Given** the number of repetitions requested is below the minimum needed to measure spread, **When** the check completes, **Then** the system presents a provisional reading explicitly marked as not statistically confident and renders neither verdict.

---

### User Story 3 - Machine-callable verdict for other agents (Priority: P3)

An autonomous agent, rather than a person, needs to check its own reasoning before acting, without any human at a screen.

The calling agent requests a check for a trading pair and receives a structured result it can branch on programmatically: the verdict, the incoherence figure, the underlying disagreement measure, the confidence interval, and how the reading compares to the stored baseline. The agent can then abandon or proceed with its intended trade on its own.

**Why this priority**: This turns the guard from a single application into reusable infrastructure any agent can call, which multiplies its reach. It reuses the same decision engine as the human-facing flow, so it adds interface surface rather than new logic.

**Independent Test**: Can be fully tested by having a separate agent request a check for a pair and confirming it receives a machine-readable verdict with all stated fields, and that the values match what the human-facing flow reports for the same configuration.

**Acceptance Scenarios**:

1. **Given** a calling agent requests a check for a pair with a stored baseline, **When** the check completes, **Then** the caller receives a structured result containing the verdict, incoherence figure, disagreement measure, confidence interval, and baseline comparison.
2. **Given** a calling agent requests a check for a configuration with no stored baseline, **When** the check completes, **Then** the caller receives an explicit no-baseline outcome distinguishable from both a pass and a veto.
3. **Given** an agent is instructed to check before trading, **When** it prepares a trade and the check returns a veto, **Then** the agent abandons the trade and reports the reason.

---

### Edge Cases

- **Probe is not currently valid**: the three legs of the constructed cycle may drift out of alignment with each other. The system must confirm the cycle is internally consistent before treating it as a valid probe, and refuse to proceed if it is not.
- **Live data unavailable**: if market data cannot be retrieved, the system fails visibly and refuses the run rather than substituting cached, remembered, or synthetic values.
- **Agent returns unusable output**: an elicitation may return a malformed or missing forecast. Individual failed samples are discarded, and if too few usable samples remain to support a reading, the run reports insufficient data rather than a verdict.
- **Configuration has changed since calibration**: changing the model, the system prompt, the data source, or the probe invalidates the stored baseline. The system treats such a run as having no baseline rather than comparing against a mismatched one.
- **Reading is better than baseline**: an agent measuring significantly *more* coherent than its baseline is not blocked, but the deviation is surfaced, since it also indicates the configuration has changed.
- **Ambiguous reading**: when the evidence does not separate the reading from the baseline at the required confidence, the outcome is a pass qualified by its confidence level, never a silently forced verdict.
- **Interrupted calibration**: a calibration that does not complete leaves no partial baseline behind.
- **Concurrent calibration**: two calibration runs for the same configuration must not produce a corrupted or interleaved baseline.

## Requirements *(mandatory)*

### Functional Requirements

**Probe construction and data integrity**

- **FR-001**: System MUST construct a probe as a closed three-leg cycle containing the user's selected trading pair, selecting the third asset from a fixed set of liquid alternatives.
- **FR-002**: System MUST retrieve the prices defining the probe from a live market data source at the time of each run.
- **FR-003**: System MUST verify that the three legs of the probe are mutually consistent within a 1% tolerance before using it, and MUST abort the run with a clear explanation if they are not.
- **FR-004**: System MUST fail visibly and abort the run whenever live market data, agent inference, or the trade quote is unavailable, and MUST NOT substitute cached, remembered, or synthetic values under any circumstance.

**Elicitation**

- **FR-005**: System MUST elicit the agent's forecasts in three separate contexts, such that no context has access to what the agent answered in any other.
- **FR-006**: System MUST show each context only the market data relevant to its own two legs, withholding information that would reveal the constraint linking all three.
- **FR-007**: System MUST repeat each context's elicitation a configurable number of times between 1 and 15.
- **FR-008**: System MUST record, for each elicited response, evidence of which model produced it and that the response was not altered in transit.
- **FR-009**: System MUST discard individual responses that cannot be interpreted as a valid forecast, and MUST report insufficient data rather than a reading when too few usable responses remain.

**Measurement**

- **FR-010**: System MUST compute, from the collected forecasts, the proportion of the agent's belief mass that falls on outcomes which cannot logically occur, and MUST report this as the headline figure.
- **FR-011**: System MUST compute the spread of that measurement across repetitions and derive a confidence interval from it.
- **FR-012**: System MUST require at least 3 repetitions per context to produce a confidence interval, and MUST return an explicit insufficient-samples state below that threshold.
- **FR-013**: System MUST NOT report any monetary figure as a measure of incoherence.

**Baseline**

- **FR-014**: System MUST store, per calibrated agent configuration, the average incoherence, its spread, and the number of samples taken.
- **FR-015**: System MUST key each stored baseline to the combination of model, system prompt, data source, and probe, such that a change to any of these results in a different key.
- **FR-016**: System MUST require between 9 and 15 repetitions per context when calibrating a baseline.
- **FR-017**: System MUST NOT store a baseline from a calibration run that did not complete.
- **FR-018**: System MUST warn the operator and require confirmation before replacing an existing baseline.

**Verdict**

- **FR-019**: System MUST decide pass or veto by comparing the current reading against the stored baseline for the same configuration, NOT against a fixed threshold.
- **FR-020**: System MUST return a veto only when the current reading is significantly worse than the baseline at the stated confidence level.
- **FR-021**: System MUST return an explicit no-baseline outcome, distinguishable from both pass and veto, when no baseline exists for the current configuration, and MUST direct the requester to calibrate.
- **FR-022**: System MUST display, alongside every verdict, the confidence level applied and the number of repetitions the reading is based on.
- **FR-023**: System MUST surface a reading that is significantly better than baseline as a pass accompanied by a notice that the configuration appears to have changed.

**Advisory gating**

- **FR-024**: System MUST render a verdict before the user can commit a trade, and MUST display that verdict alongside the trade.
- **FR-025**: System MUST NOT prevent the user from proceeding. On a veto or no-baseline outcome it MUST require an explicit, deliberate acknowledgement of the warning before the commit action proceeds; on a pass it MUST allow the commit action without additional friction.
- **FR-025a**: The warning shown on a veto MUST state what was measured and what it does and does not imply — specifically that drift from baseline indicates the agent's reasoning has changed, not that the trade is unprofitable.
- **FR-026**: System MUST obtain a real, executable quote for the user's trade before gating it.
- **FR-027**: System MUST NOT transmit any transaction to a live network in this scope; the advisory verdict and its acknowledgement are the extent of the action. (Wallet connection and real execution are an explicitly scoped stretch — see Out of Scope.)

**Interfaces**

- **FR-028**: System MUST stream partial results to the operator as each context's elicitation completes, rather than only on completion of the whole run.
- **FR-029**: System MUST expose the same decision engine to calling agents, returning a structured result containing verdict, incoherence figure, disagreement measure, confidence interval, and baseline comparison.
- **FR-030**: System MUST produce identical verdicts through the human-facing and machine-facing interfaces for the same configuration and inputs.

**Honesty**

- **FR-031**: System MUST NOT present coherence as evidence of correctness, profitability, or the absence of manipulation in any surface presented to a user.

### Key Entities

- **Agent Configuration**: The subject under test. Identified by the underlying model and the system prompt given to it. Distinct from the party requesting the check.
- **Probe**: A closed three-leg cycle of trading pairs constructed around the user's chosen pair, whose legs are mathematically constrained to be mutually consistent. Serves as the instrument, not as a trade anyone intends to make.
- **Elicitation Sample**: One forecast returned by the agent for one context on one repetition, carrying evidence of which model produced it.
- **Health Baseline**: A stored record of an agent configuration's normal incoherence — average, spread, and sample count — keyed to model, prompt, data source, and probe.
- **Coherence Reading**: The result of one check: the incoherence figure, the underlying disagreement measure, and the confidence interval around it.
- **Verdict**: The decision derived by comparing a reading to a baseline — pass, veto, or no-baseline — always accompanied by its confidence level and repetition count.
- **Trade Request**: The pair, amount, and quote the user intends to commit, whose commit action is gated by the verdict.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can obtain a published health figure for a previously uncalibrated agent in a single sitting, without writing anything or consulting documentation beyond the interface.
- **SC-002**: A gating check completes and renders a verdict within 45 seconds at the default repetition setting.
- **SC-003**: 100% of rendered verdicts display both the confidence level applied and the number of repetitions the reading is based on.
- **SC-004**: The system renders neither a pass nor a veto in 100% of cases where no baseline exists for the requested configuration.
- **SC-005**: The system renders neither a pass nor a veto in 100% of cases where repetitions fall below the minimum required to measure spread.
- **SC-006**: Repeating calibration on an unchanged agent configuration produces a health figure whose confidence interval overlaps the original.
- **SC-007**: Introducing a deliberate degradation into a calibrated agent's inputs produces a veto, while the same agent left untouched produces a pass.
- **SC-008**: A calling agent can obtain a verdict and act on it without any human interaction, and the verdict matches what the human-facing interface reports for the same configuration.
- **SC-009**: The system completes zero runs using substituted, cached, or synthetic market data — every completed run is traceable to live data retrieved during that run.
- **SC-010**: Every elicited forecast contributing to a verdict carries evidence of which model produced it.

## Assumptions

- **Operator and end user are the same person.** No role separation, account system, or access control is in scope; the demonstration is single-user.
- **A trade is never transmitted to a live network.** The commit action's availability is the deliverable; nothing is settled on-chain, so no wallet, signing, or slippage handling is in scope.
- **95% confidence is the standard applied** to both the confidence interval around a reading and the comparison against baseline, unless an operator specifies otherwise.
- **The baseline comparison is one-sided for gating purposes**: only a significantly *worse* reading produces a veto. A significantly better reading passes but is flagged, since it likewise indicates the configuration changed.
- **Baselines do not expire on a timer.** A stored baseline remains valid until one of its key components — model, prompt, data source, or probe — changes. Time-based staleness is out of scope.
- **The default repetition count for gating is 3**, the minimum that permits a spread estimate; the range 1–15 is exposed so speed can be traded against confidence.
- **The third leg of the probe is chosen automatically** by liquidity from a small fixed set of alternatives; the user does not select it.
- **A single agent configuration may hold multiple baselines**, one per probe, since the probe forms part of the baseline key.
- **Coherence is a necessary but not sufficient condition** for sound agent behaviour. An agent may pass this check and still be wrong. This limitation is stated in the product's own surfaces rather than assumed away.
- **Uniform degradation is not detectable by this method.** The check detects fragmented or asymmetric inconsistency between contexts; an agent whose beliefs shift consistently in one direction will pass.

## Dependencies

The following are externally imposed constraints on this feature rather than freely chosen options. They are recorded here because they bound what the solution may assume:

- **Live decentralized market data** must be the source of the prices defining the probe. Mocked, cached, or static data disqualifies the result.
- **Verifiable inference** must produce every elicited forecast, such that each response carries cryptographic evidence of which model generated it and that it was not altered.
- **Real executable quotes** must back the gated trade, so the blocked action corresponds to a trade that could genuinely have been made.
- **Two interfaces over one engine** are required: a browser-based operator view and a machine-callable interface for other agents, sharing identical decision logic.

## Out of Scope

- **Wallet connection, transaction signing, and on-chain submission — deferred as a scoped stretch goal, not abandoned.** The advisory model is designed to accommodate it: when execution lands, acknowledging the warning submits the trade rather than ending the flow. Deferred because the approval → permit2 → submit path costs roughly 2 hours and puts real funds at risk during judging.
- Multi-user accounts, authentication, or authorization.
- Time-based baseline expiry or scheduled re-calibration.
- Sweeping multiple probes per check to strengthen the constraint set.
- Any claim, surface, or metric asserting that coherence predicts profit or loss.
- Detection of uniformly biased agents.
