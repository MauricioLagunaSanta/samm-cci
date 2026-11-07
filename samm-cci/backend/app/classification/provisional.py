"""Clasificación PROVISIONAL (maqueta) de TIPO y sentimiento.

Sirve para ver el Excel y el dashboard funcionando antes de tener los boletines. NO es el
clasificador definitivo ni se guarda en la base de datos: se recalcula cada vez.

  * TIPO: sin boletines no se puede saber si una nota "deriva de un comunicado". Se usa una señal
    indirecta: si el MISMO titular (o casi) aparece en 2 o más medios distintos, lo más probable es
    que salga de un boletín -> "Réplica". Una nota que aparece en un solo medio -> "Mención".
    Es una heurística: puede equivocarse en ambos sentidos (p. ej. un hecho que cubren varios
    medios por su cuenta, o una réplica que solo publicó un medio).
  * Sentimiento: conteo de palabras de un léxico mínimo en titular+resumen. Es muy tosco; la Fase
    definitiva usará un modelo en español (pysentimiento) y se medirá contra el Excel histórico.

La Fase definitiva reemplaza este módulo: cuando una nota tenga `boletin_id`, su tipo manda.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.classification.relevance import normalize
from app.models import FuenteOrigen, Mencion, Sentimiento, TipoRegistro

UMBRAL_DEFECTO = 80  # similitud de titulares (0-100) para considerar que es la misma nota

# Palabras completas (ya sin tildes). Léxico deliberadamente corto y conservador.
POSITIVAS = frozenset(
    "lanza lanzo lanzamiento inaugura inauguro logra logro premia premio reconoce reconocimiento "
    "crecimiento exito exitoso impulsa fortalece apoya celebra alianza beneficia oportunidades "
    "record destaca gana ganador ganadora felicita".split()
)
NEGATIVAS = frozenset(
    "denuncia critica crisis cierre quiebra polemica demanda sancion investigacion irregularidades "
    "cae caida perdida rechaza queja escandalo corrupcion fraude cancelan cancelado suspende "
    "suspension accidente amenaza".split()
)


@dataclass(frozen=True)
class InfoClasif:
    tipo: TipoRegistro
    sentimiento: Sentimiento
    grupo: int | None  # número de grupo de réplicas (None si es mención)
    n_medios: int  # medios distintos en el grupo (1 si es mención)
    score: float | None  # mejor similitud con otra nota del grupo
    primera_del_grupo: bool  # la más antigua del grupo (para escribir el conteo una sola vez)


def sentimiento_lexico(texto: str) -> Sentimiento:
    palabras = normalize(texto).split()
    pos = sum(p in POSITIVAS for p in palabras)
    neg = sum(p in NEGATIVAS for p in palabras)
    if pos > neg:
        return Sentimiento.POSITIVO
    if neg > pos:
        return Sentimiento.NEGATIVO
    return Sentimiento.NEUTRO


def _clave_medio(m: Mencion) -> str:
    return (m.dominio or m.medio or f"id{m.id}").lower()


def _orden_fecha(m: Mencion):
    return (m.fecha_publicacion.replace(tzinfo=None) if m.fecha_publicacion else None) or m.fecha_monitoreo


def clasificar(notas: Sequence[Mencion], umbral: int = UMBRAL_DEFECTO) -> dict[int, InfoClasif]:
    """Devuelve {id_nota: InfoClasif} para las notas dadas (normalmente las de un mes)."""
    notas = sorted(notas, key=lambda m: (str(_orden_fecha(m)), m.id))
    titulos = [normalize(m.titular) for m in notas]
    n = len(notas)
    padre = list(range(n))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    mejor = [0.0] * n
    for i in range(n):
        for j in range(i + 1, n):
            if _clave_medio(notas[i]) == _clave_medio(notas[j]):
                continue  # el mismo medio actualizando su nota no es una réplica
            r = fuzz.token_sort_ratio(titulos[i], titulos[j])
            if r >= umbral:
                padre[raiz(i)] = raiz(j)
                mejor[i] = max(mejor[i], r)
                mejor[j] = max(mejor[j], r)

    miembros: dict[int, list[int]] = {}
    for i in range(n):
        miembros.setdefault(raiz(i), []).append(i)

    resultado: dict[int, InfoClasif] = {}
    grupo_no = 0
    for idxs in sorted(miembros.values(), key=lambda g: g[0]):
        medios = {_clave_medio(notas[i]) for i in idxs}
        es_replica = len(idxs) >= 2 and len(medios) >= 2
        if es_replica:
            grupo_no += 1
        for pos_, i in enumerate(idxs):
            m = notas[i]
            texto = f"{m.titular} {m.resumen or ''}"
            resultado[m.id] = InfoClasif(
                tipo=TipoRegistro.REPLICA if es_replica else TipoRegistro.MENCION,
                sentimiento=m.sentimiento or sentimiento_lexico(texto),
                grupo=grupo_no if es_replica else None,
                n_medios=len(medios) if es_replica else 1,
                score=mejor[i] if es_replica else None,
                primera_del_grupo=pos_ == 0,
            )
    return resultado


def tipo_efectivo(m: Mencion, info: InfoClasif) -> TipoRegistro:
    """Lo etiquetado por una persona (histórico) o ya asociado a un boletín manda sobre el provisional."""
    if m.tipo != TipoRegistro.SIN_CLASIFICAR and (m.boletin_id is not None or m.origen == FuenteOrigen.HISTORICO):
        return m.tipo
    return info.tipo
