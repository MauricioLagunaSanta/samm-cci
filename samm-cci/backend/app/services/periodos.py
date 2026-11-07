"""Utilidades de periodos: a qué mes (hora de Colombia) pertenece cada nota."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EstadoRelevancia, Mencion
from app.services.pipeline import COLOMBIA

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
_MES_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def fecha_local(m: Mencion) -> date:
    """Fecha de publicación en hora de Colombia; si el medio no la informó, el día de monitoreo."""
    dt = m.fecha_publicacion
    if dt is None:
        return m.fecha_monitoreo
    if dt.tzinfo is None:  # SQLite devuelve datetimes sin zona: se guardaron en UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(COLOMBIA).date()


def parse_mes(texto: str) -> tuple[int, int]:
    """'2026-10' -> (2026, 10). Lanza ValueError si el formato no es AAAA-MM."""
    m = _MES_RE.match(texto or "")
    if not m:
        raise ValueError("Formato de mes inválido; use AAAA-MM (ej. 2026-10)")
    return int(m.group(1)), int(m.group(2))


def mes_str(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def nombre_mes(anio: int, mes: int) -> str:
    return f"{MESES[mes - 1].upper()} {anio}"


def desplazar_mes(anio: int, mes: int, delta: int) -> tuple[int, int]:
    idx = anio * 12 + (mes - 1) + delta
    return idx // 12, idx % 12 + 1


def _por_mes(session: Session, estado: EstadoRelevancia) -> dict[tuple[int, int], list[Mencion]]:
    filas = session.scalars(select(Mencion).where(Mencion.estado_relevancia == estado)).all()
    grupos: dict[tuple[int, int], list[Mencion]] = defaultdict(list)
    for m in filas:
        f = fecha_local(m)
        grupos[(f.year, f.month)].append(m)
    return grupos


def validas_por_mes(session: Session) -> dict[tuple[int, int], list[Mencion]]:
    return _por_mes(session, EstadoRelevancia.VALIDA)


def revisar_por_mes(session: Session) -> dict[tuple[int, int], list[Mencion]]:
    return _por_mes(session, EstadoRelevancia.REVISAR)


def meses_disponibles(session: Session) -> list[str]:
    claves = set(validas_por_mes(session)) | set(revisar_por_mes(session))
    return [mes_str(*k) for k in sorted(claves, reverse=True)]
