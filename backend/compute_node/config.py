import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ComputeSettings:
    service_name: str
    port: int
    node_id: str = "S1"
    share_index: int = 1
    internal_service_token: str = "change-me-local-demo"


def get_settings() -> ComputeSettings:
    node_id = os.getenv("COMPUTE_NODE_ID", "S1").upper()
    if node_id not in {"S1", "S2"}:
        raise ValueError("COMPUTE_NODE_ID must be S1 or S2")
    default_port = 8201 if node_id == "S1" else 8202
    return ComputeSettings(
        service_name=os.getenv("SERVICE_NAME", f"compute-{node_id.lower()}"),
        port=int(os.getenv("PORT", str(default_port))),
        node_id=node_id,
        share_index=1 if node_id == "S1" else 2,
        internal_service_token=os.getenv("INTERNAL_SERVICE_TOKEN", "change-me-local-demo"),
    )
