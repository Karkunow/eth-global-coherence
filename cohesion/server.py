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
from cohesion.orchestrator import AgentConfig, ProbeInvalid, run_calibration

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
