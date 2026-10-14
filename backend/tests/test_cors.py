from fastapi.testclient import TestClient

from control_plane.config import ControlSettings, get_settings
from control_plane.main import create_app


def cors_client(tmp_path, cors_origins=None):
    settings = ControlSettings(
        database_url=f"sqlite:///{(tmp_path / 'cors.db').as_posix()}",
        cors_origins=tuple(cors_origins or ["http://localhost:5173", "http://127.0.0.1:5173"]),
    )
    return TestClient(create_app(settings))


def test_default_cors_origins_are_only_local_dev_origins(tmp_path) -> None:
    settings = ControlSettings(
        database_url=f"sqlite:///{(tmp_path / 'cors-default.db').as_posix()}"
    )
    assert "http://localhost:5173" in settings.cors_origins
    assert "http://127.0.0.1:5173" in settings.cors_origins
    assert "*" not in settings.cors_origins


def test_cors_origins_can_be_configured_by_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS", "https://frontend.example.com, https://dev.example.com"
    )
    settings = get_settings()
    assert settings.cors_origins == (
        "https://frontend.example.com",
        "https://dev.example.com",
    )


def test_allowed_origin_receives_cors_header(tmp_path) -> None:
    client = cors_client(tmp_path)
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_disallowed_origin_does_not_receive_cors_header(tmp_path) -> None:
    client = cors_client(tmp_path)
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_is_allowed_for_configured_origin(tmp_path) -> None:
    client = cors_client(tmp_path)
    response = client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
