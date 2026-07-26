"""stdio MCP server exposing the same engine as the dashboard (FR-029).
Transport only (plan.md) -- every tool is a thin wrapper around
orchestrator.run_check()/run_calibration(), with zero decision logic of
its own. This is what makes FR-030 (identical verdicts from both
interfaces) true by construction rather than by discipline.
"""
from mcp.server.fastmcp import FastMCP

from cohesion import baseline
from cohesion.config import load_config
from cohesion.graph_client import DataUnavailable
from cohesion.inference import InferenceUnavailable
from cohesion.orchestrator import AgentConfig, ProbeInvalid, run_calibration, run_check
from cohesion.uniswap import QuoteUnavailable

mcp = FastMCP("cohesion")
_cfg = load_config()


@mcp.tool()
def coherence_check(pair: str, amount: str, model: str | None = None,
                     prompt_id: str = "default", reps: int = 3) -> dict:
    """Check whether an AI agent's beliefs about a swap pair are internally
    coherent before trading. Call this before executing any swap. Returns
    PASS (safe to proceed), VETO (agent has drifted from its calibrated
    baseline -- do not proceed), or NO_BASELINE (this agent configuration
    has never been calibrated; no judgment is possible). The 'model'
    argument names the agent being MEASURED, which is not necessarily you
    -- the caller invoking this tool is never the subject.
    """
    pair_t = tuple(pair.split("-"))
    agent_config = AgentConfig(model=model or _cfg.zg_model)
    try:
        verdict = None
        for evt in run_check(_cfg, agent_config, pair_t, float(amount), reps, prompt_id=prompt_id):
            if evt.event == "verdict":
                verdict = evt.data
        return verdict if verdict is not None else {"error": "NO_VERDICT_PRODUCED"}
    except ProbeInvalid as e:
        return {"error": "PROBE_INVALID", "detail": str(e), "product": e.probe.product}
    except DataUnavailable as e:
        return {"error": "DATA_UNAVAILABLE", "detail": str(e)}
    except QuoteUnavailable as e:
        return {"error": "QUOTE_UNAVAILABLE", "detail": str(e)}
    except InferenceUnavailable as e:
        return {"error": "INFERENCE_UNAVAILABLE", "detail": str(e)}
    except ValueError as e:
        return {"error": "INSUFFICIENT_DATA", "detail": str(e)}


@mcp.tool()
def coherence_calibrate(pair: str, model: str, prompt_id: str = "default",
                         reps: int = 12, overwrite: bool = False) -> dict:
    """Establish a coherence baseline for an agent configuration. Required
    before coherence_check can return PASS or VETO. Takes several minutes
    (27-45 model calls). Run once per configuration; re-run only when the
    model, system prompt, data source, or pair changes.
    """
    pair_t = tuple(pair.split("-"))
    agent_config = AgentConfig(model=model)
    try:
        stored, exists = None, None
        for evt in run_calibration(_cfg, agent_config, pair_t, reps, prompt_id=prompt_id, overwrite=overwrite):
            if evt.event == "exists":
                exists = evt.data
            elif evt.event == "stored":
                stored = evt.data
        if stored is not None:
            return {"stored": True, **stored}
        if exists is not None:
            return {"stored": False, "reason": "BASELINE_EXISTS", "existing": exists}
        return {"stored": False, "reason": "UNKNOWN"}
    except ProbeInvalid as e:
        return {"stored": False, "reason": "PROBE_INVALID", "detail": str(e)}
    except DataUnavailable as e:
        return {"stored": False, "reason": "DATA_UNAVAILABLE", "detail": str(e)}
    except InferenceUnavailable as e:
        return {"stored": False, "reason": "INFERENCE_UNAVAILABLE", "detail": str(e)}
    except ValueError as e:
        return {"stored": False, "reason": "INSUFFICIENT_DATA", "detail": str(e)}


@mcp.tool()
def coherence_baselines() -> dict:
    """List stored coherence baselines. Use this to check whether an agent
    configuration has been calibrated before calling coherence_check."""
    return {"baselines": [b.to_dict() for b in baseline.list_baselines()]}


if __name__ == "__main__":
    mcp.run()
