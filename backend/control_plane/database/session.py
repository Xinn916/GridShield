from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def database_type_from_url(database_url: str) -> str:
    backend = make_url(database_url).get_backend_name()
    if backend == "sqlite":
        return "SQLite"
    if backend == "postgresql":
        return "PostgreSQL"
    return backend.replace("_", " ").title()


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_tables(factory: sessionmaker[Session]) -> None:
    import control_plane.models  # noqa: F401

    engine = factory.kw["bind"]
    Base.metadata.create_all(engine)
    # These ALTER statements only preserve compatibility with earlier local
    # SQLite demo databases. Fresh PostgreSQL schemas are created completely by
    # metadata.create_all; future production schema changes must use migrations.
    if engine.dialect.name != "sqlite":
        return
    columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
    migrations = {
        "grant_id": "ALTER TABLE tasks ADD COLUMN grant_id VARCHAR(40)",
        "calculation_mode": "ALTER TABLE tasks ADD COLUMN calculation_mode VARCHAR(16) NOT NULL DEFAULT 'PLAIN'",
        "started_at": "ALTER TABLE tasks ADD COLUMN started_at DATETIME",
        "completed_at": "ALTER TABLE tasks ADD COLUMN completed_at DATETIME",
        "duration_ms": "ALTER TABLE tasks ADD COLUMN duration_ms INTEGER",
        "epsilon": "ALTER TABLE tasks ADD COLUMN epsilon FLOAT NOT NULL DEFAULT 1.0",
        "privacy_unit": "ALTER TABLE tasks ADD COLUMN privacy_unit VARCHAR(32) NOT NULL DEFAULT 'household'",
        "sensitivity_json": "ALTER TABLE tasks ADD COLUMN sensitivity_json TEXT",
        "mechanism": "ALTER TABLE tasks ADD COLUMN mechanism VARCHAR(48) NOT NULL DEFAULT 'none'",
        "budget_status": "ALTER TABLE tasks ADD COLUMN budget_status VARCHAR(16) NOT NULL DEFAULT 'NOT_REQUIRED'",
        "budget_before": "ALTER TABLE tasks ADD COLUMN budget_before FLOAT",
        "budget_after": "ALTER TABLE tasks ADD COLUMN budget_after FLOAT",
    }
    with engine.begin() as connection:
        for name, statement in migrations.items():
            if name not in columns:
                connection.execute(text(statement))

    audit_columns = {column["name"] for column in inspect(engine).get_columns("task_audits")}
    audit_migrations = {
        "group_by": "ALTER TABLE task_audits ADD COLUMN group_by VARCHAR(8)",
        "bucket_count": "ALTER TABLE task_audits ADD COLUMN bucket_count INTEGER",
        "dataset_versions_json": "ALTER TABLE task_audits ADD COLUMN dataset_versions_json TEXT NOT NULL DEFAULT '{}'",
    }
    with engine.begin() as connection:
        for name, statement in audit_migrations.items():
            if name not in audit_columns:
                connection.execute(text(statement))

    security_columns = {column["name"] for column in inspect(engine).get_columns("security_audits")}
    security_migrations = {
        "target_user_id": "ALTER TABLE security_audits ADD COLUMN target_user_id VARCHAR(64)",
        "import_id": "ALTER TABLE security_audits ADD COLUMN import_id VARCHAR(64)",
        "source_sha256": "ALTER TABLE security_audits ADD COLUMN source_sha256 VARCHAR(64)",
        "row_count": "ALTER TABLE security_audits ADD COLUMN row_count INTEGER",
        "import_status": "ALTER TABLE security_audits ADD COLUMN import_status VARCHAR(16)",
        "operation": "ALTER TABLE security_audits ADD COLUMN operation VARCHAR(64)",
    }
    with engine.begin() as connection:
        for name, statement in security_migrations.items():
            if name not in security_columns:
                connection.execute(text(statement))

    user_columns = {column["name"] for column in inspect(engine).get_columns("demo_users")}
    user_migrations = {
        "last_login_at": "ALTER TABLE demo_users ADD COLUMN last_login_at DATETIME",
    }
    with engine.begin() as connection:
        for name, statement in user_migrations.items():
            if name not in user_columns:
                connection.execute(text(statement))


def session_dependency(factory: sessionmaker[Session]):
    def get_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return get_session
