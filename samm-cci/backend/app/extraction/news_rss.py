"""Extractor de Google News RSS.

Google News devuelve cada resultado con el titular en formato "Titular - Medio" y un enlace de
redirección. Este módulo separa el titular exacto del nombre del medio y entrega objetos
`RawItem` listos para que el pipeline los valide, deduplique y guarde.
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import httpx

from app.config import get_settings

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class RawItem:
    titular: str
    url_google: str
    medio: str | None
    dominio_medio: str | None  # de <source url="...">, útil si no se puede resolver la URL
    resumen: str | None
    publicado: datetime | None
    consulta: str


def build_feed_url(query: str, ventana: str, hl: str, gl: str, ceid: str) -> str:
    q = f"{query} when:{ventana}" if ventana else query
    return f"{GOOGLE_NEWS_RSS}?q={quote_plus(q)}&hl={hl}&gl={gl}&ceid={ceid}"


def split_title(raw_title: str, medio: str | None) -> tuple[str, str | None]:
    """Separa 'Titular - Medio' en (titular, medio).

    Si el RSS informa el medio en <source>, se quita exactamente ese sufijo. Si no, se corta
    en el ÚLTIMO ' - ' (los titulares pueden contener guiones; el medio va siempre al final).
    """
    title = html.unescape(raw_title).strip()
    if medio and title.endswith(f" - {medio}"):
        return title[: -len(f" - {medio}")].strip(), medio
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        if head and len(tail) <= 80:
            return head.strip(), medio or tail.strip()
    return title, medio


def _clean_summary(raw: str | None) -> str | None:
    if not raw:
        return None
    text = html.unescape(_TAG_RE.sub(" ", raw))
    return re.sub(r"\s+", " ", text).strip() or None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_feed(xml_text: str, consulta: str) -> list[RawItem]:
    """Convierte el XML del RSS en RawItem. Es pura (sin red): se prueba offline."""
    feed = feedparser.parse(xml_text)
    items: list[RawItem] = []
    for entry in feed.entries:
        raw_title = entry.get("title")
        link = entry.get("link")
        if not raw_title or not link:  # titular y URL son obligatorios
            continue
        source = entry.get("source") or {}
        medio_rss = source.get("title") if hasattr(source, "get") else None
        dominio = None
        if hasattr(source, "get") and source.get("href"):
            dominio = source["href"].split("//")[-1].split("/")[0].lower().removeprefix("www.")
        titular, medio = split_title(raw_title, medio_rss)
        if not titular:
            continue
        items.append(
            RawItem(
                titular=titular,
                url_google=link,
                medio=medio,
                dominio_medio=dominio,
                resumen=_clean_summary(entry.get("summary")),
                publicado=_parse_date(entry.get("published")),
                consulta=consulta,
            )
        )
    return items


def fetch_query(
    query: str,
    *,
    ventana: str,
    hl: str,
    gl: str,
    ceid: str,
    client: httpx.Client | None = None,
) -> list[RawItem]:
    """Descarga y parsea una consulta. Lanza httpx.HTTPError si la red/Google falla."""
    settings = get_settings()
    url = build_feed_url(query, ventana, hl, gl, ceid)
    own_client = client is None
    client = client or httpx.Client(
        timeout=settings.http_timeout,
        headers={"User-Agent": settings.http_user_agent},
        follow_redirects=True,
    )
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return parse_feed(resp.text, query)
    finally:
        if own_client:
            client.close()


def get_queries(config: dict) -> list[str]:
    """Consultas fijas + una por cada evento clave con `buscar: true` (sin duplicados)."""
    queries = list(config["google_news"]["consultas"])
    for ev in config.get("eventos", []):
        if ev.get("buscar", True):
            queries.append(f'"{ev["nombre"]}"')
    return list(dict.fromkeys(queries))


def fetch_all(config: dict, delay: float | None = None) -> tuple[list[RawItem], list[str]]:
    """Corre todas las consultas de sources.yaml. Devuelve (items, errores)."""
    settings = get_settings()
    delay = settings.request_delay if delay is None else delay
    gn = config["google_news"]
    items: list[RawItem] = []
    errors: list[str] = []
    with httpx.Client(
        timeout=settings.http_timeout,
        headers={"User-Agent": settings.http_user_agent},
        follow_redirects=True,
    ) as client:
        for i, query in enumerate(get_queries(config)):
            if i:
                time.sleep(delay)
            try:
                items.extend(
                    fetch_query(
                        query,
                        ventana=gn.get("ventana", "2d"),
                        hl=gn["hl"],
                        gl=gn["gl"],
                        ceid=gn["ceid"],
                        client=client,
                    )
                )
            except httpx.HTTPError as exc:
                errors.append(f"{query}: {exc}")
    return items, errors
