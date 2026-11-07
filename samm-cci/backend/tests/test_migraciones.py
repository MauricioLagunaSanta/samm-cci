from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.database import Base, make_engine, migrar


def _engine(tmp_path, nombre="m.db"):
    from app import models  # noqa: F401

    return make_engine(f"sqlite:///{(tmp_path / nombre).as_posix()}")


def _version(engine):
    with engine.connect() as c:
        return c.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_base_nueva_queda_identica_a_los_modelos(tmp_path):
    engine = _engine(tmp_path)
    migrar(engine)
    assert _version(engine) == "0002"
    with engine.connect() as conn:
        diferencias = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diferencias == []  # si el modelo cambia sin migración, esta prueba falla


def test_base_anterior_a_alembic_conserva_sus_datos(tmp_path):
    engine = _engine(tmp_path, "fase4.db")
    Base.metadata.create_all(engine)  # así la dejaron las Fases 2-4
    with engine.begin() as conn:
        for col in ("tipo_contenido", "redes", "observaciones", "archivo_origen"):
            conn.execute(text(f"ALTER TABLE menciones DROP COLUMN {col}"))
        conn.execute(
            text(
                "INSERT INTO menciones (titular, url, url_canonica, url_resuelta, origen, cuerpo_ok, "
                "estado_relevancia, tipo, fecha_captura, fecha_monitoreo) VALUES "
                "('Nota vieja', 'https://a.com/1', 'https://a.com/1', 1, 'GOOGLE_NEWS', 0, 'VALIDA', "
                "'MENCION', '2026-10-01', '2026-10-01')"
            )
        )
    migrar(engine)
    migrar(engine)  # ejecutarlo dos veces no rompe nada
    assert _version(engine) == "0002"
    assert {"redes", "archivo_origen"} <= {c["name"] for c in inspect(engine).get_columns("menciones")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT titular FROM menciones")).scalar() == "Nota vieja"
