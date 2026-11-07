"""Reporte de importación: qué entró, qué se omitió y cada anomalía con archivo/hoja/fila."""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Anomalia:
    archivo: str
    hoja: str
    fila: int
    codigo: str
    detalle: str = ""


@dataclass
class Reporte:
    dry_run: bool = False
    archivos: int = 0
    filas_leidas: int = 0
    duplicados_descartados: int = 0
    ya_existentes: int = 0
    importadas: int = 0
    boletines_creados: int = 0
    por_mes: Counter = field(default_factory=Counter)
    por_tipo: Counter = field(default_factory=Counter)
    anomalias: list[Anomalia] = field(default_factory=list)

    def anomalia(self, fila, codigo: str, detalle: str = "") -> None:
        self.anomalias.append(Anomalia(fila.archivo, fila.hoja, fila.fila, codigo, detalle))

    def texto(self) -> str:
        lineas = [
            ("SIMULACRO (no se guardó nada)" if self.dry_run else "IMPORTACIÓN TERMINADA"),
            f"  Archivos: {self.archivos} · filas leídas: {self.filas_leidas}",
            f"  Duplicados entre hojas/archivos descartados: {self.duplicados_descartados}",
            f"  Ya estaban en la base: {self.ya_existentes}",
            f"  {'Se importarían' if self.dry_run else 'Importadas'}: {self.importadas} "
            f"· boletines {'detectados' if self.dry_run else 'creados'}: {self.boletines_creados}",
            "  Por tipo: " + ", ".join(f"{k}={v}" for k, v in sorted(self.por_tipo.items())),
            "  Por mes:  " + ", ".join(f"{k}={v}" for k, v in sorted(self.por_mes.items())),
        ]
        codigos = Counter(a.codigo for a in self.anomalias)
        if codigos:
            detalle = ", ".join(f"{k}={v}" for k, v in codigos.most_common())
            lineas.append(f"  Anomalías ({len(self.anomalias)}): {detalle}")
        return "\n".join(lineas)

    def a_csv(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:  # utf-8-sig: Excel lo abre bien
            w = csv.writer(fh)
            w.writerow(["archivo", "hoja", "fila", "codigo", "detalle"])
            for a in self.anomalias:
                w.writerow([a.archivo, a.hoja, a.fila, a.codigo, a.detalle])
