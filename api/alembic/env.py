"""Alembic environment. The DB URL comes from DATABASE_URL (config.Settings),
or `alembic -x db_url=postgresql://...` (used by the tests)."""

from logging.config import fileConfig

from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import engine_from_config, pool

from config import get_settings
from db.models import Base
from db.session import sqlalchemy_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

db_url = context.get_x_argument(as_dictionary=True).get("db_url") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", sqlalchemy_url(db_url or get_settings().database_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    # Let autogenerate/`alembic check` reflect pgvector columns.
    connection.dialect.ischema_names["vector"] = Vector
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if (connection := config.attributes.get("connection")) is not None:
        _run(connection)
        return
    engine = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
