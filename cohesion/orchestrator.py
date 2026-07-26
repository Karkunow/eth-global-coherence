"""Composes graph_client + triangle + inference + core into the shared
progress-event scaffolding that both run_calibration() (US1) and
run_check() (US2) build on. This is the only module that knows the full
sequence (plan.md) — server.py and mcp_server.py are transport only.

Progress events are yielded, not returned, so both the SSE server and the
MCP server can consume the same generator: the server translates each
ProgressEvent into an SSE `event:`/`data:` pair (FR-028 — streamed as each
elicitation lands, never batched), while a non-streaming caller can just
drain the generator and keep the last `reading`/`verdict` event.
"""
from dataclasses import dataclass

import numpy as np

from cohesion import baseline, core, graph_client, triangle
from cohesion.config import Config
from cohesion.inference import elicit


@dataclass(frozen=True)
class ProgressEvent:
    event: str  # "probe" | "quote" | "baseline" | "sample" | "reading" | "verdict" | "done" | "error"
    data: dict


@dataclass(frozen=True)
class AgentConfig:
    """The subject under test -- never the caller (contracts/mcp-tools.md's
    'two distinct agents' distinction). Identified by model + system_prompt,
    both of which participate in the baseline key (FR-015)."""
    model: str
    system_prompt: str | None = None
    provider: str = "zg"


class ProbeInvalid(Exception):
    def __init__(self, probe: triangle.Probe):
        self.probe = probe
        super().__init__(f"probe product {probe.product} outside 1% tolerance of 1.0")


def _select_third_asset(cfg: Config, pair: tuple) -> str:
    candidates = {
        c: graph_client.fetch_candidate_tvl(cfg, pair[1], c) for c in triangle.LIQUID_THIRD_ASSETS
    }
    return triangle.pick_third_asset(candidates)


def build_and_validate_probe(cfg: Config, pair: tuple) -> triangle.Probe:
    """Selects the third leg by TVL, fetches the live triangle, and checks
    the closed-cycle product. Raises ProbeInvalid rather than proceeding
    on a probe that isn't currently arbitrage-tight (FR-003)."""
    third = _select_third_asset(cfg, pair)
    legs = graph_client.fetch_triangle_legs(cfg, pair, third)
    probe = triangle.build_probe(pair, third, legs, graph_client.now_iso())
    if not probe.valid:
        raise ProbeInvalid(probe)
    return probe


def probe_event(probe: triangle.Probe) -> ProgressEvent:
    return ProgressEvent("probe", {
        "pair": list(probe.pair),
        "third": probe.third,
        "product": probe.product,
        "valid": probe.valid,
        "fetched_at": probe.fetched_at,
        "legs": [
            {"pool_address": leg.pool_address, "token0": leg.token0, "token1": leg.token1,
             "price": leg.price, "fee_tier": leg.fee_tier, "tvl_usd": leg.tvl_usd}
            for leg in probe.legs
        ],
    })


def elicit_contexts(cfg: Config, probe: triangle.Probe, reps: int, confidence: float = 0.95,
                     agent_config: AgentConfig | None = None):
    """Sequential elicitation across all three contexts x reps (research D8:
    concurrency triggers 429/503 on 0G's router, so this is deliberately a
    plain nested loop, not asyncio.gather). Yields a `sample` ProgressEvent
    as each elicitation lands, then a final `reading` ProgressEvent carrying
    the assembled CoherenceReading plus discard accounting (FR-028).

    Returns (reading, samples_by_context) via the generator's return value
    -- callers that need trial-level stats (baseline storage, the drift
    test) should capture it with `reading, samples = yield from
    elicit_contexts(...)` rather than reaching into this generator's
    internals.
    """
    context_slices = triangle.build_all_context_slices(probe)
    samples_by_context = {ctx: [] for ctx in core.CONTEXTS}
    discarded = 0
    model = agent_config.model if agent_config else None
    system_prompt = agent_config.system_prompt if agent_config else None

    for ctx in core.CONTEXTS:
        prompt = triangle.build_prompt(context_slices[ctx])
        if system_prompt:
            prompt = f"{system_prompt}\n\n{prompt}"
        for rep in range(reps):
            result = elicit(cfg, prompt, model=model)
            used = result.distribution is not None
            if used:
                samples_by_context[ctx].append(result.distribution)
            else:
                discarded += 1
            attestation = result.attestation
            yield ProgressEvent("sample", {
                "context": f"{ctx[0]},{ctx[1]}",
                "rep": rep,
                "used": used,
                "distribution": list(result.distribution) if used else None,
                "disagreement": (result.distribution[1] + result.distribution[2]) if used else None,
                "attestation": {
                    "model_reported": attestation.model_reported,
                    "response_id": attestation.response_id,
                    "provider_address": attestation.provider_address,
                    "verifiability": attestation.verifiability,
                } if attestation else None,
            })

    samples_used = sum(len(v) for v in samples_by_context.values())
    if samples_used == 0:
        reading = core.CoherenceReading(
            incoherence=0.0, disagreement_sum=0.0, std_error=None, ci_low=None, ci_high=None,
            reps=0, signalling=0.0, samples_used=0, samples_discarded=discarded,
        )
    else:
        reading = core.analyse(samples_by_context, confidence=confidence)
        reading = core.CoherenceReading(
            incoherence=reading.incoherence, disagreement_sum=reading.disagreement_sum,
            std_error=reading.std_error, ci_low=reading.ci_low, ci_high=reading.ci_high,
            reps=reading.reps, signalling=reading.signalling,
            samples_used=samples_used, samples_discarded=discarded,
        )

    yield ProgressEvent("reading", {
        "incoherence": float(reading.incoherence),
        "disagreement_sum": float(reading.disagreement_sum),
        "std_error": float(reading.std_error) if reading.std_error is not None else None,
        "ci_low": float(reading.ci_low) if reading.ci_low is not None else None,
        "ci_high": float(reading.ci_high) if reading.ci_high is not None else None,
        "reps": reading.reps,
        "signalling": float(reading.signalling),
        "samples_used": reading.samples_used,
        "samples_discarded": reading.samples_discarded,
    })
    return reading, samples_by_context


def run_calibration(cfg: Config, agent_config: AgentConfig, pair: tuple, reps: int,
                     prompt_id: str = "default", overwrite: bool = False,
                     path: str = baseline.BASELINES_PATH):
    """IDLE -> FETCHING_POOLS -> [product check] -> ELICITING (reps x 3
    contexts) -> COMPUTING -> CONFIRMING_OVERWRITE? -> STORED.

    Any failure (ProbeInvalid, InferenceUnavailable, ValueError) propagates
    as an exception rather than being swallowed here -- store_baseline() is
    only reached after this generator runs to completion, so an interrupted
    run never writes a partial baseline (FR-017).
    """
    if not (9 <= reps <= 15):
        raise ValueError(f"calibration requires reps between 9 and 15, got {reps}")

    probe = build_and_validate_probe(cfg, pair)
    yield probe_event(probe)

    key = baseline.compute_key(
        agent_config.model, prompt_id, "graph", baseline.probe_descriptor(pair, probe.third)
    )
    existing = baseline.load_baseline(key, path=path)
    if existing and not overwrite:
        yield ProgressEvent("exists", {
            "key": key, "calibrated_at": existing.calibrated_at, "n": existing.n,
        })
        return

    reading, samples_by_context = yield from elicit_contexts(
        cfg, probe, reps, confidence=cfg.confidence, agent_config=agent_config
    )

    trials = core.disagreement_sum_trials(samples_by_context)
    if len(trials) < 2:
        raise ValueError("too few usable samples to calibrate a baseline (need >= 2 trials)")

    stored = baseline.Baseline(
        key=key, model=agent_config.model, prompt_id=prompt_id, pair=pair, third=probe.third,
        mean_incoherence=float(reading.incoherence),
        mean_disagreement_sum=float(np.mean(trials)),
        std_dev=float(np.std(trials, ddof=1)),
        n=len(trials),
        calibrated_at=graph_client.now_iso(),
    )
    baseline.store_baseline(stored, path=path)

    yield ProgressEvent("stored", {
        "key": stored.key,
        "mean_incoherence": stored.mean_incoherence,
        "mean_disagreement_sum": stored.mean_disagreement_sum,
        "std_dev": stored.std_dev,
        "n": stored.n,
        "calibrated_at": stored.calibrated_at,
    })
