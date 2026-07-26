# Judge Presentation Script

Companion script for the [judge deck](../README.md) (8 slides). Short theses per slide, meant to be
spoken loosely, not read verbatim. After slide 8, hand off to a live demo and conclusions.

## 1 — Title

- Cohesion: a reasoning health check for AI agents, before they move money.
- One line: this isn't about whether the agent is *right* — it's about whether it's *consistent with
  itself*.

## 2 — The Problem

- TEE attestation is everywhere in this space right now — it proves *who* spoke.
- It proves nothing about *whether what was said holds together*.
- Every model has some baseline incoherence, even honest ones — that's the gap we measure.

## 3 — The Core Insight

- A swap pair naturally closes a triangle — X/Y, Y/Z, Z/X.
- Ask three yes/no questions, one per leg, but in three completely separate conversations — the
  agent never sees the whole triangle.
- Pure arithmetic: in every possible world, exactly two of the three pairs disagree. So the three
  disagreement probabilities *must* sum to 2.0.
- If it comes in under 2.0, the same question got a different answer depending on what it was
  paired with — that's the tell.

## 4 — How It Works

- Four real steps, three real sponsor integrations doing actual work, not decoration.
- Same engine powers both the browser dashboard and an MCP tool other agents can call — one
  codepath, so it can't disagree with itself.

## 5 — The Gate

- The twist: we don't gate on perfect coherence, because nothing achieves that.
- We gate on *drift* from this specific agent's own calibrated normal.
- Statistical test, not a vibe — Welch's t-test against its own history.
- Advisory only. It never blocks a trade outright — it makes you look at the number first.

## 6 — Real Numbers

- Six real models, six real calibrated scores, live on mainnet.
- Explicitly not a leaderboard — lower isn't "smarter," just more self-consistent under this probe.

## 7 — Three Sponsors

- Quick beat on each: Graph = the data the whole triangle is built from. 0G = where every belief
  query actually runs, honestly labeled. Uniswap = a real transaction a real wallet can actually
  sign and send.

## 8 — Live Demo

- Hand off here — "let's see it live" — then into your demo and conclusions.
