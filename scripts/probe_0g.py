#!/usr/bin/env python3
"""End-to-end probe of the 0G Compute Router, plus the D10 variance sweep.

Answers the questions the build branches on:

  O1  Does the Router return per-response attestation the caller can see?
      This decides whether the dashboard may say "cryptographically verified"
      or only "model reported by provider". Conflating those overclaims.

  O2  Does the funded account actually produce an inference call?
      A wallet balance proves tokens exist, not that the ledger opened or
      that a provider accepts them.

  D10 Does the subject model produce genuine sampling variance on the real
      production prompt? A single successful call (the default run below)
      does NOT answer this — only repeated sampling does. qwen2.5-omni on
      testnet returned 32/32 identical responses across every sampling
      parameter tried (see research.md D10). Re-run this sweep against
      every new model before trusting it as a measurement subject.

Run:
  python scripts/probe_0g.py              # single call: balance, auth, O1, parse
  python scripts/probe_0g.py --sweep       # D10 methodology: repeated sampling,
                                            # reports sd — REQUIRED before trusting
                                            # a model, not optional

Reads network/model from .env (ZG_RPC_URL, ZG_API_BASE, ZG_MODEL, ZG_API_KEY).
Defaults below match .env.example's current target — see that file for the
testnet-vs-mainnet rationale (research D10: testnet's only chat model failed
the sweep; mainnet is now the target).
"""
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API_BASE = "https://router-api.0g.ai/v1"
DEFAULT_RPC = "https://evmrpc.0g.ai"
DEFAULT_MODEL = "claude-opus-4-8"

# The real production prompt shape (persona + explicit correlation instruction +
# live-style market data). This is deliberate: an earlier, more abstract prompt
# showed variance on qwen2.5-omni that this shape did not (research D10) — a
# generic probe would have missed the actual problem. Probing with anything
# less specific than this proves connectivity, not usability.
def build_prompt(nonce=""):
    tag = f"[t:{nonce}] " if nonce else ""
    return f"""{tag}You are a crypto market analyst producing a calibrated joint forecast.
LIVE MARKET DATA (last 24 hours, spot):
  WETH: $3891.44  24h +1.82%  range $3810.12-$3925.60
  USDC: $1.00  24h +0.01%  range $0.998-$1.002
RELEVANT RATIOS:
  WETH/USDC = 3891.44  (24h change +1.81%)

X = the WETH/USDC price ratio 24 hours from now is HIGHER than it is right now
Y = the USDC/WBTC price ratio 24 hours from now is HIGHER than it is right now
Give your joint probability distribution over the four possible outcomes.
Account for how X and Y are related to each other and what the data above implies.

Reply with ONLY a JSON object, no prose, no markdown fence:
{{"p_XY_both_true": <float>, "p_X_true_Y_false": <float>, "p_X_false_Y_true": <float>, "p_both_false": <float>}}
The four numbers must sum to 1.0."""


def load_env():
    try:
        for line in open(".env"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20)).get("result")


def call(api_base, key, model, text, temp=1.0, extra=None, tries=3):
    """One elicitation with backoff. Returns (parsed_dict_or_None, error_str_or_None, headers, raw_body)."""
    payload = {"model": model, "messages": [{"role": "user", "content": text}],
               "max_tokens": 150, "temperature": temp}
    if extra:
        payload.update(extra)
    body = json.dumps(payload).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                f"{api_base}/chat/completions", data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            resp = urllib.request.urlopen(req, timeout=90)
            raw = resp.read().decode()
            headers = dict(resp.headers)
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            import re
            m = re.search(r"\{[^{}]*\}", content, re.S)
            parsed = json.loads(m.group(0)) if m else None
            return parsed, None, headers, data
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return None, f"HTTP {e.code}: {detail}", {}, {}
        except Exception as e:
            return None, f"{type(e).__name__}: {e}", {}, {}
    return None, "exhausted retries", {}, {}


def cmd_single(api_base, rpc_url, key, addr, model):
    """Default mode: balance, one call, O1 attestation surface, parse check."""
    print("=" * 68)
    print(f"  0G Compute Router probe — single call")
    print(f"  network: {api_base}")
    print("=" * 68)

    if addr:
        try:
            bal = int(rpc(rpc_url, "eth_getBalance", [addr, "latest"]), 16) / 1e18
            chain = int(rpc(rpc_url, "eth_chainId", []), 16)
            print(f"\n[balance] {addr}\n          {bal:.4f} 0G  (chain {chain})")
            print("          need >= 4 (3 ledger + 1 provider)")
        except Exception as e:
            print(f"[balance] check failed: {e}")

    if not key:
        print("\n✗ ZG_API_KEY not set. Create one at the network's compute portal,")
        print("  deposit >= 3 0G into the ledger, fund a provider (1 0G), then retry.\n")
        return 1

    print(f"\n[inference] model={model}")
    parsed, err, headers, data = call(api_base, key, model, build_prompt("single"))
    if err:
        print(f"  ✗ {err}")
        if "402" in err or "403" in err:
            print("\n  -> auth OK but ledger not funded / provider not accepted yet.")
        elif "401" in err:
            print("\n  -> key rejected.")
        elif "429" in err:
            print("\n  -> rate limited even on a single call — unusual, check account state.")
        return 1
    print("  ✓ call succeeded")

    print("\n" + "=" * 68)
    print("  O1 — attestation surface")
    print("=" * 68)
    ATTEST_HDRS = ("zg-res-key", "x-provider", "zg-signature", "x-zg-signature", "x-attestation")
    found_h = {k: v for k, v in headers.items() if k.lower() in ATTEST_HDRS}
    trace = data.get("x_0g_trace", {})
    print("\n[headers]")
    print("  " + ("\n  ".join(f"{k}: {v}" for k, v in found_h.items()) if found_h else "(none)"))
    print("\n[x_0g_trace]")
    print("  " + (json.dumps(trace) if trace else "(absent)"))

    has_provider_id = bool(found_h.get("X-Provider") or trace.get("provider"))
    has_signature = any("sign" in k.lower() for k in found_h) or "signature" in trace
    print("\n[verdict on O1 — precise wording matters]")
    if has_signature:
        print("  ✓ CRYPTOGRAPHIC SIGNATURE present. May be described as 'verified'.")
    elif has_provider_id:
        print("  ⚠ Provider IDENTITY present (address + response key), NO signature.")
        print("    Correct UI wording: 'model and provider reported by 0G Compute,")
        print("    with a response key that permits verification' — NOT 'verified'.")
        print("    (Zg-Res-Key is a handle for the TS SDK's processResponse(), not")
        print("    proof by itself. Confirmed on testnet 2026-07-26 — re-check per network.)")
    else:
        print("  ✗ No attestation-shaped data found at all. FR-008 at risk — investigate.")

    print("\n" + "=" * 68)
    print("  Elicitation parses?")
    print("=" * 68)
    if not parsed:
        print("\n  ✗ no JSON parsed — sample would be discarded (FR-009).")
        return 1
    vals = [float(parsed[k]) for k in ("p_XY_both_true", "p_X_true_Y_false",
                                        "p_X_false_Y_true", "p_both_false")]
    total = sum(vals)
    print(f"\n  ✓ {[round(v,4) for v in vals]}  sum={total:.4f} "
          f"{'✓' if abs(total-1) < 0.02 else '⚠ needs normalizing'}")
    print(f"  P(X != Y) = {vals[1]+vals[2]:.4f}")
    print("\n  ⚠ ONE CALL PROVES PARSING, NOT USABILITY.")
    print("    Run `--sweep` before trusting this model as a measurement subject —")
    print("    see research.md D10 for why a single success is not enough.")
    return 0


def cmd_sweep(api_base, key, model, n=8, temp=1.0):
    """D10 methodology: repeated sampling on the real prompt, report variance."""
    print("=" * 68)
    print(f"  D10 variance sweep — model={model}  N={n}  temp={temp}")
    print("  (sequential, unique nonce per call — matches research.md D10 exactly)")
    print("=" * 68 + "\n")

    if not key:
        print("✗ ZG_API_KEY not set.")
        return 1

    disagreements = []
    errors = 0
    t_start = time.time()
    for i in range(n):
        nonce = f"{time.time():.6f}-{i}"
        parsed, err, _, _ = call(api_base, key, model, build_prompt(nonce), temp=temp)
        if err:
            print(f"  rep {i}: ERROR {err}")
            errors += 1
            continue
        d = parsed["p_X_true_Y_false"] + parsed["p_X_false_Y_true"]
        disagreements.append(d)
        print(f"  rep {i}: {parsed}  ->  P(X!=Y)={d:.4f}")
    elapsed = time.time() - t_start

    print(f"\n{'='*68}")
    print(f"  {len(disagreements)}/{n} usable ({errors} errors), {elapsed:.1f}s total")
    if len(disagreements) < 2:
        print("  ✗ too few samples to assess variance")
        return 1
    mean = statistics.mean(disagreements)
    sd = statistics.stdev(disagreements)
    se = sd / (len(disagreements) ** 0.5)
    print(f"  mean={mean:.4f}  sd={sd:.4f}  std_error(n={len(disagreements)})={se:.4f}")
    if sd < 1e-6:
        print(f"\n  ✗ ZERO VARIANCE — {model} is not usable as a measurement subject.")
        print("    std_error would be 0; the CI and drift test are degenerate.")
        print("    This is what happened with qwen2.5-omni on testnet (research D10).")
        print("    Do not proceed with this model — try a different one.")
        return 1
    else:
        print(f"\n  ✓ REAL VARIANCE — {model} is usable. CI and drift test will be meaningful.")
        return 0


def main():
    load_env()
    api_base = os.environ.get("ZG_API_BASE", DEFAULT_API_BASE).rstrip("/")
    rpc_url = os.environ.get("ZG_RPC_URL", DEFAULT_RPC)
    key = os.environ.get("ZG_API_KEY", "").strip()
    addr = os.environ.get("ZG_ADDRESS", "").strip()
    model = os.environ.get("ZG_MODEL", DEFAULT_MODEL).strip()

    if "--sweep" in sys.argv:
        n = 8
        if "--n" in sys.argv:
            n = int(sys.argv[sys.argv.index("--n") + 1])
        return cmd_sweep(api_base, key, model, n=n)
    return cmd_single(api_base, rpc_url, key, addr, model)


if __name__ == "__main__":
    sys.exit(main())
