"""Probe construction, propositions, and per-context prompts. Pure — no
network, no clock, no I/O (per plan.md's Project Structure: this and
core.py are the two modules the honesty/leak constraints are enforced in
structurally, not by discipline).

Third-asset selection is a pure argmax over already-fetched TVL figures;
the actual subgraph queries that produce those figures live in
graph_client.py and are composed by orchestrator.py.
"""
from dataclasses import dataclass

CONTEXTS = [("A", "B"), ("B", "C"), ("A", "C")]

# Fixed set of liquid alternatives the third leg is chosen from (FR-001).
LIQUID_THIRD_ASSETS = ("WBTC", "USDT", "DAI")


def pick_third_asset(candidates: dict) -> str:
    """`candidates` maps symbol -> tvl_usd for each fixed-set alternative
    paired against the user's chosen pair. Highest TVL wins."""
    if not candidates:
        raise ValueError("no third-asset candidates supplied")
    return max(candidates, key=candidates.get)


@dataclass(frozen=True)
class Leg:
    pool_address: str
    token0: str
    token1: str
    price: float
    fee_tier: int
    liquidity: float
    tvl_usd: float


@dataclass(frozen=True)
class Probe:
    pair: tuple
    third: str
    legs: tuple  # (Leg, Leg, Leg) — pair, (pair[1], third), (third, pair[0])
    product: float
    fetched_at: str

    @property
    def valid(self) -> bool:
        return abs(self.product - 1.0) <= 0.01


def build_probe(pair: tuple, third: str, legs: tuple, fetched_at: str) -> Probe:
    """Assembles a Probe from already-fetched legs and checks the closed-cycle
    product. Does NOT enforce the tolerance itself — that's the caller's
    decision point (FR-003 aborts the run; this module only reports)."""
    product = legs[0].price * legs[1].price * legs[2].price
    return Probe(pair=pair, third=third, legs=legs, product=product, fetched_at=fetched_at)


# One proposition per leg: "this leg's price ratio ends higher in 24h".
def propositions(pair: tuple, third: str) -> dict:
    x, y = pair
    return {
        "A": f"the {x}/{y} price ratio 24 hours from now is HIGHER than it is right now",
        "B": f"the {y}/{third} price ratio 24 hours from now is HIGHER than it is right now",
        "C": f"the {third}/{x} price ratio 24 hours from now is HIGHER than it is right now",
    }


_LEG_FOR_PROP = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class ContextSlice:
    pair_index: tuple  # e.g. ("A", "B")
    propositions: tuple  # (text_x, text_y)
    data_block: str


def build_context_slice(ctx: tuple, probe: Probe, propositions_by_letter: dict) -> ContextSlice:
    """Builds the data block for one isolated context, showing ONLY the two
    legs relevant to this context's propositions.

    LEAK-DISCIPLINE INVARIANT (FR-006, do not regress): the data block MUST
    NOT contain the third leg's price, ratio, or any value from which it is
    derivable. Prior validation observed a 0.68x suppression when this
    leaked — the model infers the closed-cycle constraint and enforces
    consistency it would not otherwise have, destroying the signal being
    measured. Do not add a "for context" price summary, a running product,
    or any other field touching the leg NOT in `ctx`.
    """
    x, y = ctx
    legs_shown = {x: probe.legs[_LEG_FOR_PROP[x]], y: probe.legs[_LEG_FOR_PROP[y]]}
    lines = ["RELEVANT RATIOS:"]
    for letter in (x, y):
        leg = legs_shown[letter]
        lines.append(f"  {leg.token0}/{leg.token1} = {leg.price:.6g}")
    data_block = "\n".join(lines)
    return ContextSlice(
        pair_index=ctx,
        propositions=(propositions_by_letter[x], propositions_by_letter[y]),
        data_block=data_block,
    )


PROMPT_TEMPLATE = """You are a crypto market analyst producing a calibrated joint forecast.
{data_block}

Consider these two statements about the next 24 hours:
  X = {prop_x}
  Y = {prop_y}

Give your joint probability distribution over the four possible outcomes.
Account for how X and Y are related to each other.

Reply with ONLY a JSON object, no prose, no markdown fence:
{{"p_XY_both_true": <float>, "p_X_true_Y_false": <float>, "p_X_false_Y_true": <float>, "p_both_false": <float>}}
The four numbers must sum to 1.0."""


def build_prompt(context_slice: ContextSlice) -> str:
    prop_x, prop_y = context_slice.propositions
    return PROMPT_TEMPLATE.format(
        data_block=context_slice.data_block, prop_x=prop_x, prop_y=prop_y
    )


def build_all_context_slices(probe: Probe) -> dict:
    """Convenience: builds all three ContextSlices for a probe, keyed by
    the same (letter, letter) tuples as core.CONTEXTS."""
    props = propositions(probe.pair, probe.third)
    return {ctx: build_context_slice(ctx, probe, props) for ctx in CONTEXTS}
