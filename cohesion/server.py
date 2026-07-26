"""FastAPI app: SSE endpoints for the dashboard, serving web/index.html.
Transport only (plan.md) — no decision logic lives here; every endpoint is
a thin translation of an orchestrator.ProgressEvent into an SSE frame.
"""
import json
import time

from fastapi import FastAPI, HTTPException, Request
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
)
from cohesion.uniswap import QuoteUnavailable, get_quote

app = FastAPI(title="Cohesion")
_cfg = load_config()


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
async def calibrate(request: Request):
    body = await request.json()
    pair = tuple(body["pair"].split("-")) if isinstance(body.get("pair"), str) else tuple(body["pair"])
    model = body["model"]
    prompt_id = body.get("prompt_id", "default")
    reps = int(body.get("reps", 12))
    overwrite = bool(body.get("overwrite", False))

    if not (9 <= reps <= 15):
        raise HTTPException(status_code=422, detail="reps must be between 9 and 15 for calibration (FR-016)")

    agent_config = AgentConfig(model=model, system_prompt=body.get("system_prompt"))
    gen = run_calibration(_cfg, agent_config, pair, reps, prompt_id=prompt_id, overwrite=overwrite)
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
    return quote_event(q).data


@app.get("/api/check")
def check(pair: str, amount: float, model: str, prompt_id: str = "default", reps: int = 3,
          system_prompt: str | None = None):
    if not (1 <= reps <= 15):
        raise HTTPException(status_code=422, detail="reps must be between 1 and 15")
    pair_t = tuple(pair.split("-"))
    agent_config = AgentConfig(model=model, system_prompt=system_prompt)
    gen = run_check(_cfg, agent_config, pair_t, amount, reps, prompt_id=prompt_id)
    return StreamingResponse(_stream(gen), media_type="text/event-stream")
