"""Verifiable inference against the 0G Compute Router, with attestation
capture. One of the three I/O boundaries (plan.md) — raises on
unavailability, no fallback (FR-004); unparseable responses are discarded
by the caller, never repaired (FR-009).

Request shaping is model-family-specific, learned the hard way against
0G's mainnet router (research D10, scripts/probe_0g.py):
  - claude-* models require the Anthropic /messages shape (x-api-key,
    anthropic-version), not /chat/completions, and do not accept
    temperature/top_p at all.
  - deepseek-* models are reasoning models that burn their entire
    max_tokens budget on hidden reasoning_content unless enable_thinking
    is explicitly set to False.
  - every request needs a browser-like User-Agent or Cloudflare 403s it
    before it reaches the router (error code 1010), unrelated to auth.
"""
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from cohesion.config import Config


class InferenceUnavailable(Exception):
    """Raised when the inference provider cannot be reached at all
    (as opposed to a single sample being discarded for bad output)."""


@dataclass(frozen=True)
class Attestation:
    model_reported: str
    response_id: str | None
    provider_address: str | None
    verifiability: str  # "reported" (no signature) or "verified" (signature present)
    signature: str | None = None


@dataclass(frozen=True)
class ElicitationResult:
    distribution: tuple | None  # (p_XY, p_X!Y, p_!XY, p_!X!Y), normalized; None if discarded
    attestation: Attestation | None
    raw: str
    error: str | None


_JSON_RE = re.compile(r"\{[^{}]*\}", re.S)
_REQUIRED_KEYS = ("p_XY_both_true", "p_X_true_Y_false", "p_X_false_Y_true", "p_both_false")


def _request(cfg: Config, prompt: str, max_tokens: int, tries: int, request_timeout: float,
             model: str | None = None) -> dict:
    model = model or cfg.zg_model
    is_claude = model.startswith("claude-")
    if is_claude:
        url = f"{cfg.zg_api_base.rstrip('/')}/messages"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
        headers = {
            "Content-Type": "application/json",
            "x-api-key": cfg.zg_api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "curl/8.4.0",
        }
    else:
        url = f"{cfg.zg_api_base.rstrip('/')}/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": max_tokens, "temperature": 1.0}
        if model.startswith("deepseek-"):
            payload["enable_thinking"] = False
        elif model.startswith("0gm-"):
            # Qwen-tokenizer models take the flag nested, not top-level --
            # confirmed live: reasoning_tokens dropped from max_tokens to 0
            # and finish_reason flipped "length" -> "stop" (0gm-1.0-35b-a3b
            # has thinking on by default and otherwise burns the whole
            # budget on reasoning_content, leaving content: null).
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cfg.zg_api_key}",
                   "User-Agent": "curl/8.4.0"}

    body = json.dumps(payload).encode()
    last_err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=request_timeout)
            raw = resp.read().decode()
            resp_headers = dict(resp.headers)
            data = json.loads(raw)
            return {"data": data, "headers": resp_headers, "is_claude": is_claude}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            last_err = f"HTTP {e.code}: {detail}"
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise InferenceUnavailable(last_err) from e
        except Exception as e:
            raise InferenceUnavailable(f"{type(e).__name__}: {e}") from e
    raise InferenceUnavailable(last_err or "exhausted retries")


def _extract_content(data: dict, is_claude: bool) -> str:
    if is_claude:
        blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    # content is None when a reasoning model burns its whole max_tokens
    # budget on hidden reasoning_content (finish_reason: "length") -- treat
    # as empty so _parse_distribution discards this one sample rather than
    # the whole run crashing on a single bad response.
    return data["choices"][0]["message"]["content"] or ""


def _extract_attestation(model: str, data: dict, headers: dict) -> Attestation:
    trace = data.get("x_0g_trace", {})
    provider_address = headers.get("x-provider") or headers.get("X-Provider") or trace.get("provider")
    response_id = headers.get("zg-res-key") or trace.get("request_id")
    has_signature = any("sign" in k.lower() for k in headers) or "signature" in trace
    signature = None
    for k, v in headers.items():
        if "sign" in k.lower():
            signature = v
            break
    return Attestation(
        model_reported=model,
        response_id=response_id,
        provider_address=provider_address,
        verifiability="verified" if has_signature else "reported",
        signature=signature,
    )


def _parse_distribution(content: str) -> tuple | None:
    m = _JSON_RE.search(content)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
        values = tuple(float(parsed[k]) for k in _REQUIRED_KEYS)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if any(v < 0 for v in values):
        return None
    total = sum(values)
    if total <= 0:
        return None
    # Normalize if close but not exact; a wildly off sum is a bad sample.
    if abs(total - 1.0) > 0.15:
        return None
    return tuple(v / total for v in values)


def elicit(cfg: Config, prompt: str, max_tokens: int = 300, tries: int = 3,
           request_timeout: float = 90.0, model: str | None = None) -> ElicitationResult:
    """One forecast against `model` (the AgentConfig under test), or
    cfg.zg_model if not given. Raises InferenceUnavailable if the provider
    cannot be reached at all; returns a result with distribution=None
    (discarded, not repaired) if the response can't be parsed into a valid
    forecast."""
    result = _request(cfg, prompt, max_tokens, tries, request_timeout, model=model)
    data, headers, is_claude = result["data"], result["headers"], result["is_claude"]
    content = _extract_content(data, is_claude)
    distribution = _parse_distribution(content)
    attestation = _extract_attestation(model or cfg.zg_model, data, headers)
    return ElicitationResult(
        distribution=distribution,
        attestation=attestation,
        raw=content,
        error=None if distribution is not None else "unparseable response",
    )
