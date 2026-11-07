from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import EstadoRelevancia, Mencion


@pytest.fixture
def engine():
    from app import models  # noqa: F401

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def db(engine):
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


_contador = {"n": 0}


def crear_nota(
    db,
    titular,
    dominio,
    publicada=None,
    *,
    estado=EstadoRelevancia.VALIDA,
    via="entidad",
    url=None,
    resumen=None,
    terminos=None,
):
    _contador["n"] += 1
    n = _contador["n"]
    publicada = publicada or datetime(2026, 10, 15, 15, 0, tzinfo=UTC)
    m = Mencion(
        titular=titular,
        url=url or f"https://{dominio}/nota-{n}",
        url_canonica=f"https://{dominio}/nota-{n}",
        url_resuelta=url is None,
        medio=dominio.split(".")[0].capitalize(),
        dominio=dominio,
        resumen=resumen,
        fecha_publicacion=publicada,
        fecha_monitoreo=date(2026, 10, 15),
        estado_relevancia=estado,
        via_relevancia=via if estado == EstadoRelevancia.VALIDA else None,
        terminos_detectados=terminos,
    )
    db.add(m)
    db.commit()
    return m
