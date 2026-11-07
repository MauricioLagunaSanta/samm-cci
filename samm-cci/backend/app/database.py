"""Motor SQLAlchemy y sesiones."""
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, future=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite ignora las llaves foráneas por defecto
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(bind: Engine | None = None) -> None:
    """Deja la base lista. Sin argumentos usa Alembic (conserva datos); con `bind` (pruebas, memoria)
    crea las tablas directamente desde los modelos."""
    from app import models  # noqa: F401  (registra los modelos)

    if bind is not None:
        Base.metadata.create_all(bind)
        _verificar_esquema(bind)
        return
    migrar(engine)


def migrar(bind: Engine) -> None:
    """Aplica las migraciones de backend/migraciones. Una base anterior a Alembic (creada con create_all)
    se marca primero en la versión 0001 para que solo reciba los cambios posteriores."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migraciones"))
    tablas = set(inspect(bind).get_table_names())
    with bind.connect() as conn:
        cfg.attributes["connection"] = conn
        if "menciones" in tablas and "alembic_version" not in tablas:
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
        conn.commit()


def _verificar_esquema(bind: Engine) -> None:
    """Con create_all no se alteran tablas existentes: si al modelo le faltan columnas, avisa."""
    insp = inspect(bind)
    for tabla in Base.metadata.sorted_tables:
        faltan = {c.name for c in tabla.columns} - {c["name"] for c in insp.get_columns(tabla.name)}
        if faltan:
            raise RuntimeError(
                f"La tabla '{tabla.name}' no tiene las columnas {sorted(faltan)}. "
                "Usa app.database.init_db() sin argumentos (Alembic) o 'python -m app.cli init-db'."
            )


@contextmanager
def session_scope(factory: sessionmaker = SessionLocal) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with SessionLocal() as session:
        yield session
