"""Entorno de Alembic: usa la misma URL y los mismos modelos que la aplicación."""
from alembic import context

from app import models  # noqa: F401  (registra los modelos en Base.metadata)
from app.config import get_settings
from app.database import Base, make_engine

config = context.config
target_metadata = Base.metadata


def _ejecutar(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite no altera tablas; el modo batch las recrea cuando hace falta
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexion = config.attributes.get("connection")  # la entrega app.database.migrar()
    if conexion is not None:
        _ejecutar(conexion)
        return
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    with make_engine(url).connect() as conn:
        _ejecutar(conn)
        conn.commit()


if context.is_offline_mode():
    raise SystemExit("Modo offline no soportado: ejecuta 'alembic upgrade head' con la base accesible.")
run_migrations_online()
