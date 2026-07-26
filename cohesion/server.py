"""FastAPI app: SSE endpoints for the dashboard, serving web/index.html.
Transport only (plan.md) — no decision logic lives here; every endpoint is
a thin translation of an orchestrator.ProgressEvent into an SSE frame.
"""
import dataclasses
import json
import os
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from cohesion import baseline
from cohesion.config import load_config
from cohesion.graph_client import DataUnavailable
from cohesion.inference import InferenceUnavailable
from cohesion.orchestrator import (
    AgentConfig,
    ProbeInvalid,
    build_and_validate_probe,
    probe_event,
    quote_event,
    run_calibration,
    run_check,
    run_check_degraded_demo,
)
from cohesion.uniswap import QuoteUnavailable, build_swap_transaction, get_quote

app = FastAPI(title="Cohesion")
_cfg = load_config()

# Public-deployment guardrail, deliberately kept outside cohesion/config.py's
# Config/load_config (FR-004's strict-required-vars machinery) since this is
# a deployment concern, not core system config -- a local dev running
# without it gets the same full-featured behavior as before it existed.
_DEMO_MODE = os.environ.get("COHESION_DEMO_MODE", "").strip().lower() in ("1", "true", "yes")


def _cfg_for(zg_api_key: str | None):
    """A caller-supplied 0G key runs that request's inference calls against
    THEIR balance instead of this deployment's -- lets a public instance
    stay open without the operator eating every visitor's compute cost.
    dataclasses.replace() returns a fresh Config (it's frozen), so this
    never mutates the shared _cfg other concurrent requests are using."""
    if zg_api_key and zg_api_key.strip():
        return dataclasses.replace(_cfg, zg_api_key=zg_api_key.strip())
    return _cfg


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream(gen, error_event: dict | None = None):
    """Translates a ProgressEvent generator into SSE frames, mapping known
    exceptions to the error codes contracts/http-api.md and
    contracts/mcp-tools.md declare. No fallback branch substitutes data on
    any of these -- the run simply ends (FR-004)."""
    t_start = time.time()
    try:
        for evt in gen:
            yield _sse(evt.event, evt.data)
    except ProbeInvalid as e:
        yield _sse("error", {"error": "PROBE_INVALID", "detail": str(e), "product": e.probe.product})
        return
    except DataUnavailable as e:
        yield _sse("error", {"error": "DATA_UNAVAILABLE", "detail": str(e)})
        return
    except InferenceUnavailable as e:
        yield _sse("error", {"error": "INFERENCE_UNAVAILABLE", "detail": str(e)})
        return
    except ValueError as e:
        yield _sse("error", {"error": "INVALID_REQUEST", "detail": str(e)})
        return
    yield _sse("done", {"elapsed_ms": int((time.time() - t_start) * 1000)})


@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.post("/api/calibrate")
async def calibrate(request: Request, x_zg_api_key: str | None = Header(default=None)):
    body = await request.json()
    zg_api_key = x_zg_api_key or body.get("zg_api_key")
    if _DEMO_MODE and not zg_api_key:
        raise HTTPException(
            status_code=403,
            detail="Calibration is disabled on this public demo instance (COHESION_DEMO_MODE) unless "
                   "you supply your own 0G API key — it costs 27-45 real inference calls per run.",
        )
    pair = tuple(body["pair"].split("-")) if isinstance(body.get("pair"), str) else tuple(body["pair"])
    model = body["model"]
    prompt_id = body.get("prompt_id", "default")
    reps = int(body.get("reps", 12))
    overwrite = bool(body.get("overwrite", False))

    if not (3 <= reps <= 15):
        raise HTTPException(status_code=422, detail="reps must be between 3 and 15 for calibration")

    agent_config = AgentConfig(model=model, system_prompt=body.get("system_prompt"))
    gen = run_calibration(_cfg_for(zg_api_key), agent_config, pair, reps, prompt_id=prompt_id, overwrite=overwrite)
    return StreamingResponse(_stream(gen), media_type="text/event-stream")


@app.get("/api/baselines")
def baselines():
    return {"baselines": [b.to_dict() for b in baseline.list_baselines()]}


@app.get("/api/pools")
def pools(pair: str):
    pair_t = tuple(pair.split("-"))
    try:
        probe = build_and_validate_probe(_cfg, pair_t)
    except DataUnavailable as e:
        raise HTTPException(status_code=503, detail={"error": "DATA_UNAVAILABLE", "detail": str(e)}) from e
    except ProbeInvalid as e:
        # Still surface the probe so the client can render why it's invalid,
        # per http-api.md: `valid: false` blocks any subsequent run (FR-003).
        return probe_event(e.probe).data
    return probe_event(probe).data


@app.get("/api/quote")
def quote(pair: str, amount: float):
    x, y = pair.split("-")
    try:
        q = get_quote(_cfg, x, y, amount)
    except QuoteUnavailable as e:
        raise HTTPException(status_code=503, detail={"error": "QUOTE_UNAVAILABLE", "detail": str(e)}) from e
    return quote_event(q, (x, y)).data


@app.get("/api/swap-tx")
def swap_tx(pair: str, amount: float):
    """Constructs the real unsigned transaction Execute would send, if
    this project ever wired up real execution -- it deliberately doesn't
    (FR-027). Never signed, never broadcast; Trading-API-only (no
    QuoterV2 fallback -- it has no calldata-building endpoint)."""
    x, y = pair.split("-")
    try:
        tx = build_swap_transaction(_cfg, x, y, amount)
    except QuoteUnavailable as e:
        raise HTTPException(status_code=503, detail={"error": "QUOTE_UNAVAILABLE", "detail": str(e)}) from e
    return dataclasses.asdict(tx)


@app.get("/api/check")
def check(pair: str, amount: float, model: str, prompt_id: str = "default", reps: int = 3,
          system_prompt: str | None = None, x_zg_api_key: str | None = Header(default=None)):
    if not (1 <= reps <= 15):
        raise HTTPException(status_code=422, detail="reps must be between 1 and 15")
    pair_t = tuple(pair.split("-"))
    agent_config = AgentConfig(model=model, system_prompt=system_prompt)
    gen = run_check(_cfg_for(x_zg_api_key), agent_config, pair_t, amount, reps, prompt_id=prompt_id)
    return StreamingResponse(_stream(gen), media_type="text/event-stream")


@app.get("/api/check-degraded-demo")
def check_degraded_demo(pair: str, amount: float, model: str, prompt_id: str = "default", reps: int = 6,
                         x_zg_api_key: str | None = Header(default=None)):
    """DEMONSTRATION ONLY -- see orchestrator.run_check_degraded_demo()'s
    docstring and research.md D11. A distinct route from /api/check,
    calling a distinct function that the real advisory-gate path never
    touches, so this endpoint's existence cannot affect a real check."""
    if not (3 <= reps <= 15):
        raise HTTPException(status_code=422, detail="reps must be between 3 and 15")
    pair_t = tuple(pair.split("-"))
    agent_config = AgentConfig(model=model)
    gen = run_check_degraded_demo(_cfg_for(x_zg_api_key), agent_config, pair_t, amount, reps, prompt_id=prompt_id)
    return StreamingResponse(_stream(gen), media_type="text/event-stream")
