"""Métricas del dashboard: comparación mensual, detalle semanal y listado de notas del mes."""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.orm import Session

from app.classification.provisional import UMBRAL_DEFECTO, InfoClasif, clasificar, tipo_efectivo
from app.models import FuenteOrigen, Mencion, Sentimiento, TipoRegistro
from app.services.periodos import (
    desplazar_mes,
    fecha_local,
    mes_str,
    meses_disponibles,
    parse_mes,
    revisar_por_mes,
    validas_por_mes,
)


def _umbral(config: dict) -> int:
    return int(config.get("clasificacion_provisional", {}).get("umbral_titular", UMBRAL_DEFECTO))


def _contar(notas: Sequence[Mencion], info: dict[int, InfoClasif]) -> dict[str, int]:
    c: Counter = Counter()
    for m in notas:
        i = info[m.id]
        c["menciones" if tipo_efectivo(m, i) == TipoRegistro.MENCION else "replicas"] += 1
        c[{Sentimiento.POSITIVO: "positivas", Sentimiento.NEGATIVO: "negativas"}.get(i.sentimiento, "neutras")] += 1
    return {k: c[k] for k in ("menciones", "replicas", "positivas", "negativas", "neutras")}


def _es_provisional(notas: Sequence[Mencion]) -> bool:
    return any(m.boletin_id is None and m.origen != FuenteOrigen.HISTORICO for m in notas)


def metricas_mensuales(session: Session, config: dict, ultimos: int = 12, hasta: str | None = None) -> dict:
    """Serie mensual continua (los meses sin datos aparecen en cero) para comparar el histórico."""
    validas = validas_por_mes(session)
    revisar = revisar_por_mes(session)
    claves = set(validas) | set(revisar)
    if not claves:
        return {"provisional": True, "meses": []}
    fin = parse_mes(hasta) if hasta else max(claves)
    ventana = [desplazar_mes(*fin, -i) for i in range(ultimos - 1, -1, -1)]

    meses, provisional = [], False
    for clave in ventana:
        notas = validas.get(clave, [])
        info = clasificar(notas, _umbral(config))
        provisional |= _es_provisional(notas)
        meses.append(
            {
                "mes": mes_str(*clave),
                "total": len(notas),
                "por_revisar": len(revisar.get(clave, [])),
                **_contar(notas, info),
            }
        )
    return {"provisional": provisional, "meses": meses}


def metricas_semanales(session: Session, config: dict, anio: int, mes: int) -> dict:
    """Semanas (lunes a domingo) que tocan el mes, contando solo las notas publicadas en el mes."""
    notas = validas_por_mes(session).get((anio, mes), [])
    info = clasificar(notas, _umbral(config))
    por_semana: dict = {}
    for m in notas:
        f = fecha_local(m)
        lunes = f - timedelta(days=f.weekday())
        por_semana.setdefault(lunes, []).append(m)
    semanas = [
        {"semana_inicio": lunes.isoformat(), "total": len(grupo), **_contar(grupo, info)}
        for lunes, grupo in sorted(por_semana.items())
    ]
    return {"provisional": _es_provisional(notas), "semanas": semanas}


def resumen_mes(session: Session, config: dict, anio: int, mes: int) -> dict:
    notas = validas_por_mes(session).get((anio, mes), [])
    info = clasificar(notas, _umbral(config))
    return {
        "mes": mes_str(anio, mes),
        "total": len(notas),
        "por_revisar": len(revisar_por_mes(session).get((anio, mes), [])),
        "provisional": _es_provisional(notas),
        **_contar(notas, info),
    }


def menciones_del_mes(session: Session, config: dict, anio: int, mes: int) -> list[dict]:
    notas = validas_por_mes(session).get((anio, mes), [])
    info = clasificar(notas, _umbral(config))
    filas = []
    for m in sorted(notas, key=lambda n: (fecha_local(n), n.id), reverse=True):
        i = info[m.id]
        filas.append(
            {
                "id": m.id,
                "titular": m.titular,
                "medio": m.medio or m.dominio,
                "fecha": fecha_local(m).isoformat(),
                "url": m.url,
                "tipo": tipo_efectivo(m, i).value,
                "sentimiento": i.sentimiento.value,
                "via": m.via_relevancia,
                "medios_en_grupo": i.n_medios,
            }
        )
    return filas


__all__ = [
    "menciones_del_mes",
    "meses_disponibles",
    "metricas_mensuales",
    "metricas_semanales",
    "resumen_mes",
]
