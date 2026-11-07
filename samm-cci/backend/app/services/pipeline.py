"""Pipeline de monitoreo: extraer -> resolver URL -> filtrar -> deduplicar -> guardar."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.news_rss import RawItem, fetch_all, get_queries
from app.extraction.url_tools import (
    canonicalize_url,
    domain_of,
    is_google_news_link,
    resolve_google_news_url,
)
from app.models import Ejecucion, EstadoEjecucion, FuenteOrigen, Mencion

# Colombia no usa horario de verano: UTC-5 fijo evita depender de la base tz en Windows.
COLOMBIA = timezone(timedelta(hours=-5), "America/Bogota")


def hoy_colombia() -> date:
    return datetime.now(COLOMBIA).date()


def normalize_headline(text: str) -> str:
    """Minúsculas, sin tildes ni puntuación: para detectar el mismo titular en el mismo medio."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def run_pipeline(
    session: Session,
    config: dict,
    *,
    items: Iterable[RawItem] | None = None,
    errors: list[str] | None = None,
    resolver: Callable[[str], str | None] | None = None,
    fecha_monitoreo: date | None = None,
) -> Ejecucion:
    """Ejecuta un ciclo completo y devuelve la fila de bitácora.

    `items`/`errors` se pueden inyectar (pruebas sin red); si no, se descargan del RSS.
    `resolver` convierte un enlace de Google News en la URL real (o None si no puede).
    """
    fecha_monitoreo = fecha_monitoreo or hoy_colombia()
    ejecucion = Ejecucion()
    session.add(ejecucion)
    session.flush()

    if items is None:
        items, errors = fetch_all(config)
    items = list(items)
    errors = list(errors or [])
    ejecucion.consultas = len(get_queries(config))
    ejecucion.encontrados = len(items)

    if resolver is None and config.get("resolver_urls", True):
        resolver = resolve_google_news_url
    excluidos = {d.lower() for d in config.get("dominios_excluidos", [])}

    # Claves ya guardadas (para saltar duplicados sin una consulta por item)
    vistas_url = set(session.scalars(select(Mencion.url_canonica)))
    vistas_titular = {
        (m.dominio, normalize_headline(m.titular))
        for m in session.execute(
            select(Mencion.dominio, Mencion.titular).where(
                Mencion.fecha_monitoreo == fecha_monitoreo
            )
        ).all()
    }

    nuevos = duplicados = descartados = 0
    for it in items:
        key_google = canonicalize_url(it.url_google)
        if key_google in vistas_url:
            duplicados += 1
            continue

        url_final, resuelta = it.url_google, False
        if resolver and is_google_news_link(it.url_google):
            real = resolver(it.url_google)
            if real:
                url_final, resuelta = real, True

        dominio = domain_of(url_final) if resuelta else (it.dominio_medio or None)
        if dominio and any(dominio == d or dominio.endswith("." + d) for d in excluidos):
            descartados += 1
            continue

        key = canonicalize_url(url_final)
        key_titular = (dominio, normalize_headline(it.titular))
        if key in vistas_url or key_titular in vistas_titular:
            duplicados += 1
            vistas_url.add(key_google)
            continue

        session.add(
            Mencion(
                titular=it.titular,
                url=url_final,
                url_google=it.url_google,
                url_canonica=key,
                url_resuelta=resuelta,
                medio=it.medio,
                dominio=dominio,
                resumen=it.resumen,
                fecha_publicacion=it.publicado,
                fecha_monitoreo=fecha_monitoreo,
                consulta=it.consulta,
                origen=FuenteOrigen.GOOGLE_NEWS,
                ejecucion_id=ejecucion.id,
            )
        )
        vistas_url.update({key, key_google})
        vistas_titular.add(key_titular)
        nuevos += 1

    ejecucion.nuevos = nuevos
    ejecucion.duplicados = duplicados
    ejecucion.descartados = descartados
    ejecucion.errores = "\n".join(errors)
    ejecucion.fin = datetime.now(UTC)
    if errors and not items:
        ejecucion.estado = EstadoEjecucion.ERROR
    elif errors:
        ejecucion.estado = EstadoEjecucion.PARCIAL
    else:
        ejecucion.estado = EstadoEjecucion.OK
    session.commit()
    return ejecucion
