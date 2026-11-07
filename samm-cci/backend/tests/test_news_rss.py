from pathlib import Path

from app.extraction.news_rss import build_feed_url, parse_feed, split_title
from app.extraction.url_tools import canonicalize_url

FIXTURE = Path(__file__).parent / "fixtures" / "google_news_sample.xml"


def test_split_title_usa_source_exacto():
    assert split_title("Titular con - guion - El Olfato", "El Olfato") == (
        "Titular con - guion",
        "El Olfato",
    )


def test_split_title_sin_source_corta_en_ultimo_guion():
    assert split_title("Nota X - Medio Y", None) == ("Nota X", "Medio Y")


def test_split_title_sin_guion():
    assert split_title("Solo titular", None) == ("Solo titular", None)


def test_parse_feed_extrae_campos_obligatorios():
    items = parse_feed(FIXTURE.read_text(encoding="utf-8"), "consulta")
    # El item sin titular se descarta: titular y URL son obligatorios
    assert len(items) == 4
    primero = items[0]
    assert primero.titular == "Cámara de Comercio de Ibagué lanza ruta exportadora"
    assert primero.medio == "El Olfato"
    assert primero.dominio_medio == "elolfato.com"
    assert primero.url_google.startswith("https://news.google.com/")
    assert primero.publicado is not None and primero.publicado.year == 2026
    assert "ruta exportadora" in primero.resumen
    assert "<" not in primero.resumen


def test_parse_feed_titular_con_guiones_internos():
    items = parse_feed(FIXTURE.read_text(encoding="utf-8"), "c")
    assert items[1].titular == "Empresarios del Tolima - hablan de formalización - La Alcaldía"
    assert items[1].medio == "Ecos del Combeima"


def test_build_feed_url_codifica_y_agrega_ventana():
    url = build_feed_url('"Cámara de Comercio de Ibagué"', "2d", "es-419", "CO", "CO:es-419")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "when%3A2d" in url
    assert "%22C%C3%A1mara" in url
    assert "ceid=CO:es-419" in url


def test_canonicalize_quita_rastreo_www_y_barra():
    a = canonicalize_url("http://www.Medio.com/nota/1/?utm_source=fb&id=7#x")
    b = canonicalize_url("https://medio.com/nota/1?id=7")
    assert a == b == "https://medio.com/nota/1?id=7"
