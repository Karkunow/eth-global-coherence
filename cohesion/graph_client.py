"""Live Uniswap v3 pool data from The Graph. One of the three I/O
boundaries (plan.md) — raises on unavailability, no cache, no fallback
(FR-002, FR-004): mocked or static data disqualifies the Graph-track
submission and there is deliberately no code path that would substitute it.
"""
from datetime import datetime, timezone

import httpx

from cohesion.config import Config
from cohesion.triangle import Leg

# Mainnet token addresses for the fixed set this probe draws from.
TOKEN_ADDRESSES = {
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
}


class DataUnavailable(Exception):
    """Raised whenever live pool data cannot be retrieved. Never caught to
    substitute cached/synthetic values — only to abort the run (FR-004)."""


_POOL_QUERY = """
query Pools($token0: String!, $token1: String!) {
  poolsA: pools(
    where: { token0: $token0, token1: $token1 }
    orderBy: totalValueLockedUSD
    orderDirection: desc
    first: 1
  ) { id token0 { symbol } token1 { symbol } token0Price token1Price feeTier liquidity totalValueLockedUSD }
  poolsB: pools(
    where: { token0: $token1, token1: $token0 }
    orderBy: totalValueLockedUSD
    orderDirection: desc
    first: 1
  ) { id token0 { symbol } token1 { symbol } token0Price token1Price feeTier liquidity totalValueLockedUSD }
}
"""


def _fetch_pool_raw(cfg: Config, symbol_x: str, symbol_y: str) -> dict:
    """Queries both possible token0/token1 orderings (address order is
    arbitrary and doesn't match our semantic X/Y order) and returns
    whichever side actually has a pool, preferring the higher-TVL one if
    both exist."""
    addr_x = TOKEN_ADDRESSES[symbol_x].lower()
    addr_y = TOKEN_ADDRESSES[symbol_y].lower()
    try:
        resp = httpx.post(
            cfg.graph_url,
            json={"query": _POOL_QUERY, "variables": {"token0": addr_x, "token1": addr_y}},
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise DataUnavailable(f"subgraph query failed for {symbol_x}/{symbol_y}: {e}") from e

    if "errors" in data:
        raise DataUnavailable(f"subgraph returned errors for {symbol_x}/{symbol_y}: {data['errors']}")

    candidates = data.get("data", {}).get("poolsA", []) + data.get("data", {}).get("poolsB", [])
    if not candidates:
        raise DataUnavailable(f"no live pool found for {symbol_x}/{symbol_y}")
    candidates.sort(key=lambda p: float(p["totalValueLockedUSD"]), reverse=True)
    return candidates[0]


def fetch_leg(cfg: Config, symbol_x: str, symbol_y: str) -> Leg:
    """Fetches the highest-TVL pool for the (symbol_x, symbol_y) pair and
    returns a Leg whose `price` is Y-per-X — i.e. P(X,Y)*P(Y,Z)*P(Z,X) == 1
    identically around a closed cycle, regardless of which token the
    subgraph happens to store as pool.token0."""
    pool = _fetch_pool_raw(cfg, symbol_x, symbol_y)
    pool_token0_symbol = pool["token0"]["symbol"]
    if pool_token0_symbol == symbol_x:
        # pool.token0 == X, pool.token1 == Y -> token0Price is "token1 per
        # token0" == Y-per-X, exactly what we want.
        price = float(pool["token0Price"])
    else:
        # pool.token0 == Y, pool.token1 == X -> token1Price is "token0 per
        # token1"... the subgraph's token1Price is the reciprocal of
        # token0Price (X-per-Y), so invert it to get Y-per-X.
        price = float(pool["token1Price"])
    return Leg(
        pool_address=pool["id"],
        token0=symbol_x,
        token1=symbol_y,
        price=price,
        fee_tier=int(pool["feeTier"]),
        liquidity=float(pool["liquidity"]),
        tvl_usd=float(pool["totalValueLockedUSD"]),
    )


def fetch_candidate_tvl(cfg: Config, pair_second: str, candidate_third: str) -> float:
    """TVL of the (pair_second, candidate_third) pool, used by
    triangle.pick_third_asset() to choose the highest-liquidity third leg.
    Returns 0.0 (never raises) if no pool exists for this candidate — a
    missing candidate should just lose the argmax, not abort the run."""
    try:
        pool = _fetch_pool_raw(cfg, pair_second, candidate_third)
        return float(pool["totalValueLockedUSD"])
    except DataUnavailable:
        return 0.0


def fetch_triangle_legs(cfg: Config, pair: tuple, third: str) -> tuple:
    """Fetches the three legs of a closed cycle: pair, (pair[1], third),
    (third, pair[0]). Raises DataUnavailable if any leg has no live pool
    (FR-004 — no partial/substituted triangle)."""
    x, y = pair
    leg_xy = fetch_leg(cfg, x, y)
    leg_yz = fetch_leg(cfg, y, third)
    leg_zx = fetch_leg(cfg, third, x)
    return (leg_xy, leg_yz, leg_zx)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
