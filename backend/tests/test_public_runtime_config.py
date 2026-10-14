from fastapi.testclient import TestClient
import pytest

from control_plane.config import ControlSettings, get_settings
from control_plane.main import create_app


def test_public_runtime_config_exposes_only_environment(tmp_path):
    settings = ControlSettings(
        database_url=f"sqlite:///{(tmp_path / 'public-config.db').as_posix()}",
        app_env="production",
    )
    response = TestClient(create_app(settings)).get("/api/v1/public/config")

    assert response.status_code == 200
    assert response.json() == {"app_env": "production"}


def test_app_env_is_validated(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")

    with pytest.raises(ValueError, match="APP_ENV"):
        get_settings()
