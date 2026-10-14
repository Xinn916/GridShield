from pathlib import Path

from fastapi.testclient import TestClient

from common.enums import OrganizationId
from compute_node.config import ComputeSettings
from compute_node.main import create_app as create_compute_app
from control_plane.config import ControlSettings
from control_plane.main import create_app as create_control_app
from party_node.config import PartySettings
from party_node.main import create_app as create_party_app


def test_party_health_does_not_require_data_file() -> None:
    settings = PartySettings(OrganizationId.ORG_A, "party-a", 8101, Path("missing.parquet"))
    response = TestClient(create_party_app(settings)).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "party-a"


def test_compute_health() -> None:
    response = TestClient(create_compute_app(ComputeSettings("compute-s1", 8201))).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_control_health(tmp_path) -> None:
    settings = ControlSettings(database_url=f"sqlite:///{(tmp_path / 'control.db').as_posix()}")
    response = TestClient(create_control_app(settings)).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "control-plane"
