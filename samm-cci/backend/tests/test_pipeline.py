from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.database import Base, make_engine
from app.extraction.news_rss import parse_feed
from app.models import EstadoEjecucion, Mencion, TipoRegistro
from app.services.pipeline import normalize_headline, run_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "google_news_sample.xml"
DIA = date(2026, 11, 2)
CONFIG = {
    "google_news": {"consultas": ["q1"]},
    "dominios_excluidos": ["camaraibague.org"],
    "resolver_urls": True,
}


@pytest.fixture
def session():
    from app import models  # noqa: F401

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def _items():
    return parse_feed(FIXTURE.read_text(encoding="utf-8"), "q1")


def _fake_resolver(url: str):
    mapa = {
        "CBMiAAA111": "https://www.elolfato.com/nota/ruta-exportadora?utm_source=g",
        "CBMiBBB222": "https://ecosdelcombeima.com/economia/formalizacion/",
        "CBMiCCC333": "https://www.camaraibague.org/boletin-1",
    }
    for clave, real in mapa.items():
        if clave in url:
            return real
    return None


def test_guarda_nuevos_descarta_excluidos_y_deduplica(session):
    ej = run_pipeline(session, CONFIG, items=_items(), resolver=_fake_resolver, fecha_monitoreo=DIA)
    assert ej.estado == EstadoEjecucion.OK
    assert (ej.encontrados, ej.nuevos, ej.duplicados, ej.descartados) == (4, 2, 1, 1)

    filas = session.scalars(select(Mencion).order_by(Mencion.id)).all()
    assert [m.dominio for m in filas] == ["elolfato.com", "ecosdelcombeima.com"]
    assert all(m.url_resuelta and m.titular and m.url for m in filas)
    assert all(m.tipo == TipoRegistro.SIN_CLASIFICAR for m in filas)
    assert filas[0].url == "https://www.elolfato.com/nota/ruta-exportadora?utm_source=g"
    assert filas[0].url_canonica == "https://elolfato.com/nota/ruta-exportadora"
    assert all(m.fecha_monitoreo == DIA for m in filas)


def test_segunda_corrida_no_duplica(session):
    run_pipeline(session, CONFIG, items=_items(), resolver=_fake_resolver, fecha_monitoreo=DIA)
    ej2 = run_pipeline(session, CONFIG, items=_items(), resolver=_fake_resolver, fecha_monitoreo=DIA)
    assert ej2.nuevos == 0
    assert session.query(Mencion).count() == 2


def test_sin_resolver_conserva_enlace_de_google(session):
    ej = run_pipeline(session, CONFIG, items=_items(), resolver=lambda u: None, fecha_monitoreo=DIA)
    assert ej.nuevos == 2  # el sitio propio se descarta por <source url>
    m = session.scalars(select(Mencion).order_by(Mencion.id)).first()
    assert m.url_resuelta is False
    assert m.url.startswith("https://news.google.com/")
    assert m.dominio == "elolfato.com"


def test_errores_de_red_marcan_parcial_o_error(session):
    ej = run_pipeline(session, CONFIG, items=[], errors=["q1: timeout"], fecha_monitoreo=DIA)
    assert ej.estado == EstadoEjecucion.ERROR
    ej = run_pipeline(
        session, CONFIG, items=_items(), errors=["q2: timeout"],
        resolver=_fake_resolver, fecha_monitoreo=DIA,
    )
    assert ej.estado == EstadoEjecucion.PARCIAL


def test_normalize_headline():
    assert normalize_headline("¡Cámara de Comercio: Ibagué!") == "camara de comercio ibague"
