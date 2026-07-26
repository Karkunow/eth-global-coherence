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

from cohesion import baseline, core, graph_client, triangle, uniswap
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
                     agent_config: AgentConfig | None = None, data_block_overrides: dict | None = None):
    """Sequential elicitation across all three contexts x reps (research D8:
    concurrency triggers 429/503 on 0G's router, so this is deliberately a
    plain nested loop, not asyncio.gather). Yields a `sample` ProgressEvent
    as each elicitation lands, then a final `reading` ProgressEvent carrying
    the assembled CoherenceReading plus discard accounting (FR-028).

    `data_block_overrides` (default None -- the real, unmodified path)
    optionally replaces specific contexts' data_block text before building
    their prompt. The ONLY caller that ever passes this is
    run_check_degraded_demo() (research D11's validated synthetic
    intervention); run_check() never does, so the real advisory-gate path
    is byte-for-byte identical to before this parameter existed.

    Returns (reading, samples_by_context) via the generator's return value
    -- callers that need trial-level stats (baseline storage, the drift
    test) should capture it with `reading, samples = yield from
    elicit_contexts(...)` rather than reaching into this generator's
    internals.
    """
    context_slices = triangle.build_all_context_slices(probe)
    if data_block_overrides:
        for ctx, override_text in data_block_overrides.items():
            cs = context_slices[ctx]
            context_slices[ctx] = triangle.ContextSlice(
                pair_index=cs.pair_index, propositions=cs.propositions, data_block=override_text
            )
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
        analysed = core.analyse(samples_by_context, confidence=confidence)
        reading = core.CoherenceReading(
            incoherence=analysed.incoherence, disagreement_sum=analysed.disagreement_sum,
            std_error=analysed.std_error, ci_low=analysed.ci_low, ci_high=analysed.ci_high,
            reps=analysed.reps, signalling=analysed.signalling,
            samples_used=samples_used, samples_discarded=discarded,
            per_context_disagreement=analysed.per_context_disagreement,
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
        "per_context_disagreement": {
            f"{ctx[0]},{ctx[1]}": float(v) for ctx, v in reading.per_context_disagreement.items()
        },
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


def quote_event(quote: uniswap.Quote) -> ProgressEvent:
    return ProgressEvent("quote", {
        "amount_in": quote.amount_in, "amount_out": quote.amount_out,
        "fee_tier": quote.fee_tier, "gas_estimate": quote.gas_estimate,
        "pool_address": quote.pool_address, "quoted_at": quote.quoted_at, "source": quote.source,
    })


def run_check(cfg: Config, agent_config: AgentConfig, pair: tuple, amount: float, reps: int,
              prompt_id: str = "default", path: str = baseline.BASELINES_PATH):
    """IDLE -> QUOTING -> FETCHING_POOLS -> [product check] -> ELICITING
    (reps x 3 contexts) -> COMPUTING -> COMPARING -> VERDICT.

    Advisory only -- there is no execute/submit/sign path anywhere in this
    module (FR-027); the verdict and its acknowledgement are the extent of
    the action (FR-025).
    """
    quote = uniswap.get_quote(cfg, pair[0], pair[1], amount)
    yield quote_event(quote)

    probe = build_and_validate_probe(cfg, pair)
    yield probe_event(probe)

    key = baseline.compute_key(
        agent_config.model, prompt_id, "graph", baseline.probe_descriptor(pair, probe.third)
    )
    existing = baseline.load_baseline(key, path=path)
    if existing:
        yield ProgressEvent("baseline", {
            "found": True, "key": existing.key,
            "mean_incoherence": existing.mean_incoherence, "n": existing.n,
        })
    else:
        yield ProgressEvent("baseline", {"found": False})

    reading, samples_by_context = yield from elicit_contexts(
        cfg, probe, reps, confidence=cfg.confidence, agent_config=agent_config
    )

    trials = core.disagreement_sum_trials(samples_by_context)
    verdict = baseline.compute_verdict(existing, reading, trials, confidence=cfg.confidence)

    yield ProgressEvent("verdict", verdict.to_dict())


def run_check_degraded_demo(cfg: Config, agent_config: AgentConfig, pair: tuple, amount: float, reps: int,
                             prompt_id: str = "default", path: str = baseline.BASELINES_PATH):
    """DEMONSTRATION ONLY -- reproduces research.md D11's validated finding
    that a direct, contradictory claim about ONE proposition (A), injected
    into exactly its two contexts, produces a genuine VETO (p=4.98e-6 in
    that run). A completely separate function from run_check(), never
    called by it, so the real advisory-gate path is unaffected by this
    function's existence (FR-004's no-synthetic-data rule applies to the
    live path; this function is not that path and must never be presented
    as if it were).

    Live pool prices and the live quote are unchanged -- only the (A,B)
    and (A,C) context data blocks are overridden with a fabricated,
    mutually-contradictory "expert consensus" claim about proposition A.
    (B,C), which never mentions A, is untouched.
    """
    quote = uniswap.get_quote(cfg, pair[0], pair[1], amount)
    yield quote_event(quote)

    probe = build_and_validate_probe(cfg, pair)
    yield ProgressEvent("demo_notice", {
        "message": (
            "SYNTHETIC DEMONSTRATION: the (A,B) and (A,C) context data below has been "
            "deliberately overridden with a fabricated, mutually-contradictory claim about "
            "proposition A to demonstrate the drift-verdict mechanism (research.md D11). "
            "This is NOT a live reading of the agent's real beliefs."
        ),
    })
    yield probe_event(probe)

    key = baseline.compute_key(
        agent_config.model, prompt_id, "graph", baseline.probe_descriptor(pair, probe.third)
    )
    existing = baseline.load_baseline(key, path=path)
    if existing:
        yield ProgressEvent("baseline", {
            "found": True, "key": existing.key,
            "mean_incoherence": existing.mean_incoherence, "n": existing.n,
        })
    else:
        yield ProgressEvent("baseline", {"found": False})

    p0, p1, p2 = probe.legs[0].price, probe.legs[1].price, probe.legs[2].price
    overrides = {
        ("A", "B"): (
            f"RELEVANT RATIOS:\n  {probe.pair[0]}/{probe.pair[1]} = {p0:.6g}\n"
            f"  {probe.pair[1]}/{probe.third} = {p1:.6g}\n\n"
            f"NOTE: Market analysts are near-unanimous that {probe.pair[0]}/{probe.pair[1]} will be "
            "LOWER in 24 hours, due to a major exchange liquidity outage triggering panic selling."
        ),
        ("A", "C"): (
            f"RELEVANT RATIOS:\n  {probe.pair[0]}/{probe.pair[1]} = {p0:.6g}\n"
            f"  {probe.third}/{probe.pair[0]} = {p2:.6g}\n\n"
            f"NOTE: Market analysts are near-unanimous that {probe.pair[0]}/{probe.pair[1]} will be "
            "HIGHER in 24 hours, due to an imminent major ETF approval announcement."
        ),
    }

    reading, samples_by_context = yield from elicit_contexts(
        cfg, probe, reps, confidence=cfg.confidence, agent_config=agent_config,
        data_block_overrides=overrides,
    )

    trials = core.disagreement_sum_trials(samples_by_context)
    verdict = baseline.compute_verdict(existing, reading, trials, confidence=cfg.confidence)

    yield ProgressEvent("verdict", verdict.to_dict())
