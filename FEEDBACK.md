# Uniswap Developer Platform — Integration Feedback

Feedback from building [Cohesion](./README.md)'s trade-quote path against the Trading API
(`trade-api.gateway.uniswap.org/v1/quote`), a required qualification artifact for the $7k
API Integration track. Integration code: [cohesion/uniswap.py](./cohesion/uniswap.py).

## What worked well

- The API key issuance was fast and self-serve — no waiting, no manual review, which mattered
  a lot on a 24-hour clock.
- `POST /v1/quote`'s response for a classic swap is genuinely good once you get the right shape.

## The friction point worth reporting

**The same request unpredictably returns two completely different response shapes.**

Calling `POST /v1/quote` with an identical payload (WETH→USDC, 1.0 WETH, `EXACT_INPUT`) returned,
across consecutive calls with no parameter changes:

- Sometimes a **CLASSIC** route: `{"routing": "CLASSIC", "quote": {"route": [...], "input": {...}, "output": {...}, "gasUseEstimate": ..., ...}}`
- Sometimes a **UniswapX/Dutch-auction order**: `{"routing": "DUTCH_V2", "quote": {"orderId": ..., "encodedOrder": ..., "permitData": {...}}}` —
  no `route`, no `gasUseEstimate`, no concrete `output` amount in the same place.

For a consumer that needs a concrete `amount_out` / `fee_tier` / `gas_estimate` / `pool_address`
(any dashboard, any downstream contract call, any risk system — not just ours), this looks bad: code written and tested against one shape will silently break the first time
the router decides to return the other, with no client-side signal that the shape changed.

**What fixed it, found by trial and error, not documentation:** adding `"protocols": ["V3"]` to
the request body reliably pins the response to CLASSIC. The more discoverable-looking parameter,
`"routingPreference"`, does **not** do this — it only accepts `BEST_PRICE` or `FASTEST` (confirmed
via the API's own validation error), neither of which controls CLASSIC vs. UniswapX routing.

**Suggested fixes**, roughly in order of value:

1. Document the two response shapes and the `protocols` parameter's role in selecting between
   them, ideally right on the `/v1/quote` reference page next to `routingPreference` — the two
   parameters look like they'd overlap in purpose, and only one of them does what a reader
   would expect.
2. Alternatively, always return a normalized subset of fields (e.g. a top-level `estimatedOutput`
   and `estimatedGas`) regardless of which routing path was chosen, so a consumer that doesn't
   care about UniswapX-specific fields doesn't need to branch on `routing` at all.
3. A response-shape example for the UniswapX/Dutch case alongside the classic one in the docs
   would have cut a real debugging session (isolating this took longer than the rest of the
   Trading API integration combined).
