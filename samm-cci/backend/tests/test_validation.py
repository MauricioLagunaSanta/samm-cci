from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import load_sources
from app.database import Base, make_engine
from app.extraction.article_parser import ArticleContent, extract_from_html
from app.models import EstadoRelevancia as E
from app.models import Mencion
from app.services.validation import revalidar, validate_pending

CONFIG = load_sources()
DIA = date(2026, 11, 2)
LARGO = "Texto de relleno sobre la economía regional y sus actores. " * 8


@pytest.fixture
def session():
    from app import models  # noqa: F401

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def _m(session, n, titular, *, resuelta=True):
    m = Mencion(
        titular=titular,
        url=f"https://medio{n}.com/nota-{n}" if resuelta else f"https://news.google.com/rss/articles/X{n}",
        url_canonica=f"https://medio{n}.com/nota-{n}",
        url_resuelta=resuelta,
        fecha_monitoreo=DIA,
    )
    session.add(m)
    session.commit()
    return m


def test_valida_descarta_y_manda_a_revisar(session):
    a = _m(session, 1, "Nota A")
    b = _m(session, 2, "Nota B")
    c = _m(session, 3, "Nota C", resuelta=False)
    d = _m(session, 4, "Nota D")
    cuerpos = {
        a.url: ArticleContent(True, LARGO + " La Cámara de Comercio de Ibagué anunció..."),
        b.url: ArticleContent(True, LARGO),
        d.url: ArticleContent(False, None, "HTTP 403"),
    }
    conteo = validate_pending(session, CONFIG, fetcher=lambda u: cuerpos[u], sleep=lambda s: None)

    assert a.estado_relevancia == E.VALIDA and a.cuerpo_ok
    assert b.estado_relevancia == E.DESCARTADA
    assert c.estado_relevancia == E.REVISAR and "no resuelta" in c.error_cuerpo
    assert d.estado_relevancia == E.REVISAR and d.error_cuerpo == "HTTP 403"
    assert dict(conteo) == {"Válida": 1, "Descartada": 1, "Revisar": 2}


def test_no_vuelve_a_validar_lo_ya_validado(session):
    _m(session, 1, "Nota A")
    llamadas = []

    def fetch(u):
        llamadas.append(u)
        return ArticleContent(True, LARGO)

    validate_pending(session, CONFIG, fetcher=fetch, sleep=lambda s: None)
    validate_pending(session, CONFIG, fetcher=fetch, sleep=lambda s: None)
    assert len(llamadas) == 1


def test_revalidar_aplica_nuevas_reglas_sin_red(session):
    m = _m(session, 1, "Nota sobre pasarela")
    validate_pending(
        session, CONFIG, sleep=lambda s: None,
        fetcher=lambda u: ArticleContent(True, LARGO + " Gran Pasarela del Tolima 2026."),
    )
    assert m.estado_relevancia == E.DESCARTADA

    nueva = {**CONFIG, "eventos": [*CONFIG["eventos"], {"nombre": "Gran Pasarela del Tolima"}]}
    conteo = revalidar(session, nueva)
    assert m.estado_relevancia == E.VALIDA and m.via_relevancia == "evento"
    assert dict(conteo) == {"Válida": 1}


def test_extract_from_html_cuerpo_valido_y_corto():
    parrafos = "".join(f"<p>{LARGO}</p>" for _ in range(2))
    ok = extract_from_html(f"<html><body><article><h1>T</h1>{parrafos}</article></body></html>")
    assert ok.ok and "economía regional" in ok.texto

    corto = extract_from_html("<html><body><article><p>Muy poco.</p></article></body></html>")
    assert not corto.ok


def test_esquema_desactualizado_avisa_con_claridad(tmp_path):
    from sqlalchemy import text

    from app.database import init_db

    engine = make_engine(f"sqlite:///{(tmp_path / 'viejo.db').as_posix()}")
    with engine.begin() as conn:  # tabla de la Fase 2: sin columnas de relevancia
        conn.execute(text("CREATE TABLE menciones (id INTEGER PRIMARY KEY, titular TEXT)"))
    with pytest.raises(RuntimeError, match="no tiene las columnas"):
        init_db(engine)
