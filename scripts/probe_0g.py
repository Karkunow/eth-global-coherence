#!/usr/bin/env python3
"""One end-to-end probe of the 0G Compute Router.

Answers the two questions the build branches on:

  O1  Does the Router return per-response attestation the caller can see?
      This decides whether the dashboard may say "cryptographically verified"
      or only "model reported by provider". Conflating those overclaims.

  O2  Does the funded testnet balance actually produce an inference call?
      A wallet balance proves tokens exist, not that the ledger opened or
      that a provider accepts them.

Run:  python scripts/probe_0g.py
Needs: ZG_API_KEY in .env (create at https://pc.testnet.0g.ai)
"""
import json
import os
import sys
import urllib.error
import urllib.request

TESTNET = "https://router-api-testnet.integratenetwork.work/v1"
RPC = "https://evmrpc-testnet.0g.ai"

# Deliberately mirrors the real elicitation shape from triangle.py: two
# propositions only, a four-cell joint, strict JSON out. Probing with a
# "say hello" prompt would prove connectivity but not that the model can
# produce the structure the LP consumes.
PROMPT = """You are a crypto market analyst producing a calibrated joint forecast.

Consider these two statements about the next 24 hours:
  X = the WETH/USDC pool price 24 hours from now is HIGHER than it is right now
  Y = the USDC/WBTC pool price 24 hours from now is HIGHER than it is right now

Give your joint probability distribution over the four possible outcomes.
Account for how X and Y are related to each other.

Reply with ONLY a JSON object, no prose, no markdown fence:
{"p_XY_both_true": <float>, "p_X_true_Y_false": <float>, "p_X_false_Y_true": <float>, "p_both_false": <float>}
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


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20)).get("result")


def main():
    load_env()
    key = os.environ.get("ZG_API_KEY", "").strip()
    addr = os.environ.get("ZG_ADDRESS", "").strip()
    model = os.environ.get("ZG_MODEL", "qwen2.5-omni").strip()

    print("=" * 68)
    print("  0G Compute Router probe")
    print("=" * 68)

    # ---- balance ---------------------------------------------------------
    if addr:
        try:
            print(f"\n[balance] {addr}")
            print(f"          {int(rpc('eth_getBalance', [addr, 'latest']), 16) / 1e18:.4f} 0G "
                  f"(chain {int(rpc('eth_chainId', []), 16)})")
            print("          need >= 4 (3 ledger + 1 provider)")
        except Exception as e:
            print(f"[balance] check failed: {e}")

    if not key:
        print("\n✗ ZG_API_KEY not set.\n")
        print("  Create one — this is a browser step, it cannot be scripted:")
        print("    1. https://pc.testnet.0g.ai")
        print("    2. Connect the wallet holding the 10 0G")
        print("    3. Deposit into the ledger (>= 3 0G)")
        print("    4. Create an API key -> paste into .env as ZG_API_KEY")
        print("\n  Then re-run this probe.")
        return 1

    # ---- the call --------------------------------------------------------
    print(f"\n[inference] model={model}")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 200,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        f"{TESTNET}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        raw = resp.read().decode()
        headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        print(f"  ✗ http {e.code}: {detail}")
        if e.code == 401:
            print("\n  -> key rejected. Regenerate at pc.testnet.0g.ai.")
        elif e.code in (402, 403):
            print("\n  -> auth OK but account not funded. Deposit >= 3 0G, then fund a")
            print("     provider sub-account (1 0G). This is O2's remaining half —")
            print("     a wallet balance is not a funded ledger.")
        elif e.code == 429:
            print("\n  -> rate limited (~30/min, 5 concurrent). Bound calibration")
            print("     concurrency with a semaphore — see research D8.")
        return 1
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")
        return 1

    data = json.loads(raw)
    print("  ✓ call succeeded")

    # ---- O1: attestation -------------------------------------------------
    print("\n" + "=" * 68)
    print("  O1 — attestation surface")
    print("=" * 68)

    ATTEST_HDRS = ("zg-res-key", "zg-signature", "zg-provider", "zg-verifiability",
                   "x-zg-signature", "x-zg-provider", "x-signature", "x-attestation")
    found_h = {k: v for k, v in headers.items() if k.lower() in ATTEST_HDRS}
    print("\n[headers]")
    print("  " + ("\n  ".join(f"{k}: {v}" for k, v in found_h.items())
                  if found_h else "(no attestation-shaped headers)"))

    top = {k: v for k, v in data.items() if k not in ("choices", "usage")}
    print("\n[top-level body fields]")
    for k, v in top.items():
        print(f"  {k}: {str(v)[:90]}")

    ATTEST_BODY = ("signature", "verifiability", "attestation", "provider",
                   "tee", "proof", "signed", "enclave")
    hits = [k for k in data if any(t in k.lower() for t in ATTEST_BODY)]

    print("\n[verdict on O1]")
    if found_h or hits:
        print("  ✓ ATTESTATION PRESENT")
        print(f"    headers: {list(found_h) or 'none'}   body: {hits or 'none'}")
        print("    -> may be described as verifiable. Capture these per sample (FR-008).")
    else:
        print("  ⚠ NO CRYPTOGRAPHIC ATTESTATION on the Router path.")
        print("    Available instead: model identity + response id, reported by the provider.")
        print("    -> This still satisfies FR-008 ('evidence of which model produced it'),")
        print("       but the UI must say 'model reported by provider', NOT 'verified'.")
        print("       For a real signature, add the TS SDK sidecar (research D4 mitigation 2).")

    # ---- usable output? --------------------------------------------------
    print("\n" + "=" * 68)
    print("  Elicitation parses?")
    print("=" * 68)
    content = data["choices"][0]["message"]["content"]
    print(f"\n[raw]\n  {content.strip()[:300]}")

    import re
    m = re.search(r"\{[^{}]*\}", content, re.S)
    if not m:
        print("\n  ✗ no JSON object found — parser must discard this sample (FR-009).")
        return 1
    try:
        d = json.loads(m.group(0))
        vals = [float(d[k]) for k in ("p_XY_both_true", "p_X_true_Y_false",
                                      "p_X_false_Y_true", "p_both_false")]
    except Exception as e:
        print(f"\n  ✗ unusable JSON ({e}) — sample would be discarded (FR-009).")
        return 1

    total = sum(vals)
    print(f"\n  ✓ parsed: {[round(v, 4) for v in vals]}")
    print(f"    sum = {total:.4f} {'✓' if abs(total - 1) < 0.02 else '⚠ needs normalizing'}")
    print(f"    P(X != Y) = {vals[1] + vals[2]:.4f}   <- one term of the disagreement sum")

    u = data.get("usage", {})
    if u:
        print(f"\n  tokens: in={u.get('prompt_tokens')} out={u.get('completion_tokens')}")
        print(f"  a reps=3 check makes 9 such calls; calibration 27-45")

    print("\n" + "=" * 68)
    print("  ✓ PROBE PASSED — 0G path is viable end to end")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
