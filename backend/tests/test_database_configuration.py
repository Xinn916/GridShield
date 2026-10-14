from pathlib import Path

from control_plane.database.session import database_type_from_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_database_type_parser_returns_only_safe_backend_names() -> None:
    assert database_type_from_url("sqlite:////app/data/control_plane.db") == "SQLite"
    assert (
        database_type_from_url(
            "postgresql+psycopg://private-user:private-password@db.internal:5432/privgrid"
        )
        == "PostgreSQL"
    )


def test_production_compose_has_private_persistent_postgres_and_demo_stays_sqlite() -> None:
    production = (PROJECT_ROOT / "compose.prod.yaml").read_text(encoding="utf-8")
    demo = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    requirements = (PROJECT_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")

    assert "image: postgres:16-alpine" in production
    assert "postgresql+psycopg://" in production
    assert "POSTGRES_PASSWORD" in production
    assert "pg_isready" in production
    assert "privgrid-postgres-data:/var/lib/postgresql/data" in production
    postgres_block = production.split("  postgres:", 1)[1].split("  control-plane:", 1)[0]
    assert "ports:" not in postgres_block
    assert "sqlite:////app/data/control_plane.db" in demo
    assert "psycopg[binary]" in requirements
