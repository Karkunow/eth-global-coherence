"""Environment configuration. Loads .env once and validates required values.

FR-004's no-substitution posture starts here: a missing required credential
raises immediately rather than falling back to a default that would let a
run silently proceed on the wrong (or no) data source.
"""
import os
from dataclasses import dataclass


def _load_dotenv(path: str = ".env") -> None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


_load_dotenv()

_REQUIRED = [
    "GRAPH_API_KEY",
    "GRAPH_SUBGRAPH_ID",
    "GRAPH_GATEWAY",
    "UNISWAP_API_KEY",
    "UNISWAP_API_BASE",
    "ETH_RPC_URL",
    "UNISWAP_QUOTER_V2",
    "ZG_API_KEY",
    "ZG_API_BASE",
    "ZG_MODEL",
]


@dataclass(frozen=True)
class Config:
    graph_api_key: str
    graph_subgraph_id: str
    graph_gateway: str
    uniswap_api_key: str
    uniswap_api_base: str
    eth_rpc_url: str
    uniswap_quoter_v2: str
    zg_api_key: str
    zg_api_base: str
    zg_model: str
    default_reps: int
    calibrate_reps: int
    confidence: float
    product_tolerance: float
    provider: str

    @property
    def graph_url(self) -> str:
        return f"{self.graph_gateway}/{self.graph_api_key}/subgraphs/id/{self.graph_subgraph_id}"


def load_config() -> Config:
    """Raises RuntimeError naming every missing var, rather than proceeding partially."""
    missing = [k for k in _REQUIRED if not os.environ.get(k, "").strip()]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): " + ", ".join(missing) +
            ". Copy .env.example to .env and fill them in."
        )
    return Config(
        graph_api_key=os.environ["GRAPH_API_KEY"],
        graph_subgraph_id=os.environ["GRAPH_SUBGRAPH_ID"],
        graph_gateway=os.environ["GRAPH_GATEWAY"],
        uniswap_api_key=os.environ["UNISWAP_API_KEY"],
        uniswap_api_base=os.environ["UNISWAP_API_BASE"],
        eth_rpc_url=os.environ["ETH_RPC_URL"],
        uniswap_quoter_v2=os.environ["UNISWAP_QUOTER_V2"],
        zg_api_key=os.environ["ZG_API_KEY"],
        zg_api_base=os.environ["ZG_API_BASE"],
        zg_model=os.environ["ZG_MODEL"],
        default_reps=int(os.environ.get("COHESION_DEFAULT_REPS", "3")),
        calibrate_reps=int(os.environ.get("COHESION_CALIBRATE_REPS", "12")),
        confidence=float(os.environ.get("COHESION_CONFIDENCE", "0.95")),
        product_tolerance=float(os.environ.get("COHESION_PRODUCT_TOLERANCE", "0.01")),
        provider=os.environ.get("COHESION_PROVIDER", "zg"),
    )
