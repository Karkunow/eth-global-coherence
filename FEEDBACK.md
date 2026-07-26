# Uniswap Developer Platform — Integration Feedback

Feedback from building [Cohesion](./README.md)'s trade-quote and swap-signing path against the
Trading API (`trade-api.gateway.uniswap.org/v1/quote` and `/v1/swap`), a required qualification
artifact for the $7k API Integration track. Integration code: [cohesion/uniswap.py](./cohesion/uniswap.py).

## What worked well

- The API key issuance was fast and self-serve — no waiting, no manual review, which mattered
  a lot on a 24-hour clock.
- `POST /v1/quote`'s response for a classic swap is genuinely good once you get the right shape.

## Friction point 1

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

## Friction point 2

**`/v1/swap` and Permit2's exact request/response shapes are not on the human-readable docs
pages — only discoverable via the AI-agent-oriented mirror, or by making live calls and
inspecting responses.**

We built a real wallet-signing flow (connect MetaMask, sign a Permit2 message, send the swap —
[cohesion/uniswap.py](./cohesion/uniswap.py)'s `build_swap_transaction_from_quote`/`get_swap_quote`,
[web/index.html](./web/index.html)'s wallet flow). Three concrete gaps hit along the way:

- **No schema on the normal doc pages.** `/docs/trading/swapping-api/getting-started` and
  `/docs/trading/swapping-api/integration-guide` describe `/v1/swap` in prose ("submit the quote
  to get a transaction") but never show the actual request/response field names. The page points
  to "the API Reference" for the real schema, but that link 404s (`/reference/trading-api`). We
  only got the real shape (`{quote, signature, permitData}` in, `{to, from, data, value, chainId,
  gasLimit, maxFeePerGas, maxPriorityFeePerGas}` out) via the `llms.mdx` AI-agent mirror of the
  same page — useful that it exists, but a human reading the normal docs has no path to it.
- **Permit2's EIP-712 typed-data structure isn't documented at all.** The Permit2 concept page
  says wallet signatures are "EIP-712-style" but never shows the actual `domain`/`types`/`values`
  object. We only learned the real structure (`PermitSingle`/`PermitDetails`, `Permit2` domain at
  `0x000000000022D473030F116dDEE9F6B43aC78BA3`) by making a live `/v1/quote` call and reading the
  `permitData` field in the response.
- **`permitTransaction`'s populated shape is unreproducible in testing.** This is the one-time
  on-chain approval transaction returned when a wallet hasn't yet approved Permit2 for a token.
  We tried multiple swapper addresses, including a fresh, never-used one, specifically to trigger
  it — every one came back `permitTransaction: null`, `isTokenApprovalApplicable` either `true`
  or `None` with no populated example either way. A developer building the approval step has no
  documented example and, per our testing, no reliable way to make the API return one to test
  against.

**Suggested fixes:**

1. Put the real `/v1/swap` request/response schema (and the Permit2 typed-data shape) on the
   normal human-readable docs pages, not only in the AI-agent mirror — or at minimum, fix the
   dead link to the API Reference.
2. Document (or fix) what actually triggers a populated `permitTransaction`, and ideally provide
   a way to force it in a sandbox/testnet environment for development purposes — right now this
   code path is effectively untestable without already holding a wallet in the exact right,
   undocumented on-chain state.
3. Note explicitly that `/v1/swap` accepts a request with `signature`/`permitData` omitted
   entirely and silently returns calldata anyway, with no warning that the returned transaction
   may be missing a required authorization. A developer who skips the permit step by mistake
   gets no signal until the transaction reverts on-chain.
