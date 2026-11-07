"""Etapa 2 del monitoreo: descargar el cuerpo de cada nota pendiente y validar su relevancia."""
from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.relevance import Reglas, Resultado, compilar_reglas, evaluar
from app.extraction.article_parser import ArticleContent, fetch_article, make_client
from app.extraction.url_tools import is_google_news_link
from app.models import EstadoRelevancia, Mencion

Fetcher = Callable[[str], ArticleContent]


def aplicar(m: Mencion, res: Resultado) -> None:
    m.estado_relevancia = res.estado
    m.via_relevancia = res.via
    m.motivo_relevancia = res.motivo
    m.terminos_detectados = " | ".join(res.terminos) or None
    m.fecha_validacion = datetime.now(UTC)


def _cuerpo_para_evaluar(m: Mencion) -> str | None:
    """Solo se evalúa el cuerpo si se extrajo bien; un cuerpo truncado no justifica descartar."""
    return m.cuerpo if m.cuerpo_ok else None


def validate_pending(
    session: Session,
    config: dict,
    *,
    fetcher: Fetcher | None = None,
    limit: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Counter:
    """Descarga y valida las notas en estado PENDIENTE. Hace commit nota por nota."""
    reglas = compilar_reglas(config)
    art_cfg = config.get("articulos", {})
    pausa = float(art_cfg.get("pausa", 1.0))

    client = None
    descargar = fetcher
    if descargar is None:
        client = make_client(art_cfg.get("timeout"))
        max_bytes = int(art_cfg.get("max_bytes", 2_000_000))

        def descargar(url: str) -> ArticleContent:
            return fetch_article(url, client, max_bytes)

    stmt = (
        select(Mencion)
        .where(Mencion.estado_relevancia == EstadoRelevancia.PENDIENTE)
        .order_by(Mencion.id)
    )
    if limit:
        stmt = stmt.limit(limit)
    pendientes = session.scalars(stmt).all()

    conteo: Counter = Counter()
    descargas = 0
    try:
        for m in pendientes:
            if m.url_resuelta and not is_google_news_link(m.url):
                if descargas:
                    sleep(pausa)
                descargas += 1
                art = descargar(m.url)
            else:
                art = ArticleContent(False, None, "URL no resuelta (solo hay enlace de Google News)")
            m.cuerpo = art.texto
            m.cuerpo_ok = art.ok
            m.error_cuerpo = art.error
            aplicar(m, evaluar(m.titular, m.resumen, _cuerpo_para_evaluar(m), reglas))
            conteo[m.estado_relevancia.value] += 1
            session.commit()
    finally:
        if client:
            client.close()
    return conteo


def revalidar(
    session: Session,
    config: dict,
    *,
    estados: list[EstadoRelevancia] | None = None,
    reglas: Reglas | None = None,
) -> Counter:
    """Reevalúa con el cuerpo YA guardado, sin red. Sirve para probar cambios en las reglas
    (nuevos eventos, alias, ventana) sobre todo el historial sin volver a descargar nada."""
    reglas = reglas or compilar_reglas(config)
    stmt = select(Mencion).where(Mencion.estado_relevancia != EstadoRelevancia.PENDIENTE)
    if estados:
        stmt = stmt.where(Mencion.estado_relevancia.in_(estados))
    conteo: Counter = Counter()
    for m in session.scalars(stmt):
        aplicar(m, evaluar(m.titular, m.resumen, _cuerpo_para_evaluar(m), reglas))
        conteo[m.estado_relevancia.value] += 1
    session.commit()
    return conteo
