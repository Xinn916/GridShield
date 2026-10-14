from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


SERVICES = {
    "control": ("control_plane.main:app", 8000, {}),
    "party-a": ("party_node.main:app", 8101, {"PARTY_ID": "ORG_A"}),
    "party-b": ("party_node.main:app", 8102, {"PARTY_ID": "ORG_B"}),
    "party-c": ("party_node.main:app", 8103, {"PARTY_ID": "ORG_C"}),
    "compute-s1": ("compute_node.main:app", 8201, {"COMPUTE_NODE_ID": "S1"}),
    "compute-s2": ("compute_node.main:app", 8202, {"COMPUTE_NODE_ID": "S2"}),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one backend service with its local defaults.")
    parser.add_argument("service", choices=SERVICES)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    app_path, default_port, environment = SERVICES[args.service]
    os.environ.update(environment)
    uvicorn.run(app_path, host=args.host, port=args.port or default_port, app_dir=str(BACKEND_DIR))


if __name__ == "__main__":
    main()
