"""Mide el acierto del clasificador provisional contra las etiquetas humanas del histórico.

  * TIPO (Mención/Réplica): se corre `clasificar` mes a mes, igual que en producción, y se compara con la
    etiqueta de la persona. Solo cuentan las filas con TIPO definido.
  * Sentimiento: solo las filas que la persona marcó como Positivo/Negativo. Una celda vacía NO se toma como
    "neutro" (en los archivos recientes la columna casi nunca se llena), así que no se evalúa.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.classification.provisional import UMBRAL_DEFECTO, clasificar, sentimiento_lexico
from app.models import FuenteOrigen, TipoRegistro
from app.services.periodos import mes_str, validas_por_mes

META = 0.95


@dataclass
class Metrica:
    total: int = 0
    aciertos: int = 0
    matriz: Counter = field(default_factory=Counter)  # (real, predicho) -> n

    @property
    def acierto(self) -> float:
        return self.aciertos / self.total if self.total else 0.0

    def anotar(self, real: str, predicho: str) -> None:
        self.total += 1
        self.aciertos += real == predicho
        self.matriz[(real, predicho)] += 1


@dataclass
class Evaluacion:
    tipo: Metrica = field(default_factory=Metrica)
    sentimiento: Metrica = field(default_factory=Metrica)
    tipo_por_mes: dict[str, Metrica] = field(default_factory=dict)
    sin_etiqueta_sentimiento: int = 0

    def texto(self) -> str:
        def bloque(titulo: str, m: Metrica) -> list[str]:
            estado = "CUMPLE" if m.acierto >= META else f"faltan {100 * (META - m.acierto):.1f} pts para el 95%"
            filas = [f"{titulo}: {m.aciertos}/{m.total} = {100 * m.acierto:.1f}%  ({estado})"]
            for (real, pred), n in sorted(m.matriz.items()):
                filas.append(f"    real {real:<9} -> predicho {pred:<9} {n}")
            return filas

        out = bloque("TIPO (Mención/Réplica)", self.tipo)
        por_mes = ", ".join(f"{k}={100 * v.acierto:.0f}%" for k, v in sorted(self.tipo_por_mes.items()))
        out.append(f"  Por mes: {por_mes}")
        out += bloque("SENTIMIENTO (solo filas marcadas)", self.sentimiento)
        out.append(f"  Filas sin etiqueta de sentimiento (no evaluadas): {self.sin_etiqueta_sentimiento}")
        return "\n".join(out)


def evaluar(session: Session, config: dict, mes: tuple[int, int] | None = None) -> Evaluacion:
    umbral = int(config.get("clasificacion_provisional", {}).get("umbral_titular", UMBRAL_DEFECTO))
    ev = Evaluacion()
    for clave, notas in sorted(validas_por_mes(session).items()):
        if mes and clave != mes:
            continue
        hist = [n for n in notas if n.origen == FuenteOrigen.HISTORICO]
        if not hist:
            continue
        info = clasificar(hist, umbral)
        por_mes = ev.tipo_por_mes.setdefault(mes_str(*clave), Metrica())
        for n in hist:
            if n.tipo != TipoRegistro.SIN_CLASIFICAR:
                ev.tipo.anotar(n.tipo.value, info[n.id].tipo.value)
                por_mes.anotar(n.tipo.value, info[n.id].tipo.value)
            if n.sentimiento is None:
                ev.sin_etiqueta_sentimiento += 1
            else:
                pred = sentimiento_lexico(f"{n.titular} {n.resumen or ''}")
                ev.sentimiento.anotar(n.sentimiento.value, pred.value)
    return ev
