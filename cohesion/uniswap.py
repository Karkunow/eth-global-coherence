"""Executable quote for the trade being gated (FR-026). Trading API is
primary -- it's the $7k API Integration track's qualification requirement
("a valid API key from the Uniswap Developer Platform") -- with QuoterV2
as a fallback if the API is unreachable. One of the three I/O boundaries
(plan.md); no cached/synthetic fallback (FR-004), only these two live
paths.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from web3 import Web3

from cohesion.config import Config
from cohesion.graph_client import TOKEN_ADDRESSES

DECIMALS = {"WETH": 18, "USDC": 6, "WBTC": 8, "USDT": 6, "DAI": 18}

QUOTER_V2_ABI = [{
    "inputs": [{
        "components": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "internalType": "struct IQuoterV2.QuoteExactInputSingleParams", "name": "params", "type": "tuple",
    }],
    "name": "quoteExactInputSingle",
    "outputs": [
        {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
        {"internalType": "uint160", "name": "sqrtPriceX96After", "type": "uint160"},
        {"internalType": "uint32", "name": "initializedTicksCrossed", "type": "uint32"},
        {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"},
    ],
    "stateMutability": "nonpayable", "type": "function",
}]


class QuoteUnavailable(Exception):
    """Raised when neither the Trading API nor the QuoterV2 fallback can
    produce a quote. No cached/synthetic substitute exists (FR-004)."""


@dataclass(frozen=True)
class Quote:
    amount_in: str
    amount_out: str
    fee_tier: int
    gas_estimate: int
    pool_address: str
    quoted_at: str
    source: str  # "trading_api" | "quoter_v2"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quote_trading_api(cfg: Config, token_in: str, token_out: str, amount_in_wei: int) -> Quote:
    payload = {
        "tokenIn": TOKEN_ADDRESSES[token_in],
        "tokenOut": TOKEN_ADDRESSES[token_out],
        "amount": str(amount_in_wei),
        "type": "EXACT_INPUT",
        "tokenInChainId": 1,
        "tokenOutChainId": 1,
        "swapper": "0x0000000000000000000000000000000000000001",
        # Forces a CLASSIC route (a single quote with a concrete route/gas
        # estimate) instead of a UniswapX/Dutch-auction order response,
        # which has a completely different shape (orderId/encodedOrder,
        # no route or gas estimate) -- confirmed live 2026-07-26, the API
        # otherwise alternates between the two unpredictably per-request.
        "protocols": ["V3"],
    }
    resp = httpx.post(
        f"{cfg.uniswap_api_base.rstrip('/')}/quote", json=payload,
        headers={"x-api-key": cfg.uniswap_api_key}, timeout=20.0,
    )
    if resp.status_code != 200:
        raise QuoteUnavailable(f"Trading API HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    q = data.get("quote", {})
    route = q.get("route") or [[]]
    first_leg = route[0][0] if route and route[0] else {}
    return Quote(
        amount_in=q.get("input", {}).get("amount", str(amount_in_wei)),
        amount_out=q["output"]["amount"],
        fee_tier=int(first_leg.get("fee", 0)),
        gas_estimate=int(q.get("gasUseEstimate", 0)),
        pool_address=first_leg.get("address", ""),
        quoted_at=_now_iso(),
        source="trading_api",
    )


def _quote_quoter_v2(cfg: Config, token_in: str, token_out: str, amount_in_wei: int, fee_tier: int) -> Quote:
    w3 = Web3(Web3.HTTPProvider(cfg.eth_rpc_url))
    contract = w3.eth.contract(address=Web3.to_checksum_address(cfg.uniswap_quoter_v2), abi=QUOTER_V2_ABI)
    params = (
        Web3.to_checksum_address(TOKEN_ADDRESSES[token_in]),
        Web3.to_checksum_address(TOKEN_ADDRESSES[token_out]),
        amount_in_wei,
        fee_tier,
        0,
    )
    try:
        # QuoterV2's quoteExactInputSingle is non-view by design (it reverts
        # to return its data) -- .call() performs an eth_call / static call,
        # never sending a real transaction. Calling it as a normal
        # transaction is the most common way to lose an hour here.
        amount_out, _sqrt_after, _ticks, gas_estimate = contract.functions.quoteExactInputSingle(params).call()
    except Exception as e:
        raise QuoteUnavailable(f"QuoterV2 call failed: {e}") from e
    return Quote(
        amount_in=str(amount_in_wei),
        amount_out=str(amount_out),
        fee_tier=fee_tier,
        gas_estimate=int(gas_estimate),
        pool_address="",
        quoted_at=_now_iso(),
        source="quoter_v2",
    )


def get_quote(cfg: Config, token_in: str, token_out: str, amount_in: float, fallback_fee_tier: int = 3000) -> Quote:
    """amount_in is in human units (e.g. 1.0 WETH); converted to wei using
    DECIMALS. Trading API primary, QuoterV2 fallback (FR-026)."""
    amount_in_wei = int(amount_in * (10 ** DECIMALS[token_in]))
    try:
        return _quote_trading_api(cfg, token_in, token_out, amount_in_wei)
    except (QuoteUnavailable, httpx.HTTPError, KeyError) as trading_api_error:
        try:
            return _quote_quoter_v2(cfg, token_in, token_out, amount_in_wei, fallback_fee_tier)
        except QuoteUnavailable as fallback_error:
            raise QuoteUnavailable(
                f"both quote paths failed -- trading_api: {trading_api_error}; quoter_v2: {fallback_error}"
            ) from fallback_error


def _main():
    """quickstart.md Scenario 2: prints a real executable quote."""
    import argparse

    from cohesion.config import load_config

    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", required=True, help="e.g. WETH-USDC")
    parser.add_argument("--amount", type=float, required=True)
    args = parser.parse_args()
    x, y = args.pair.split("-")

    cfg = load_config()
    q = get_quote(cfg, x, y, args.amount)
    print(f"{args.amount} {x} -> {q.amount_out} {y} (raw units)")
    print(f"fee_tier={q.fee_tier}  gas_estimate={q.gas_estimate}  pool={q.pool_address}  source={q.source}")


if __name__ == "__main__":
    _main()
