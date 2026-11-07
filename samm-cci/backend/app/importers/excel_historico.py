"""Lectura tolerante de los Excel mensuales "Monitoreo de Medios" (CM-F-005).

Lo que aprendimos de los 10 archivos reales:
  * Las filas 1-3 son el bloque corporativo; el encabezado está en la fila 4 (se busca, no se asume).
  * Las columnas varían entre archivos (26 o 27; COSTO/PRECIO; FECHA y COSTO intercambiadas): se mapea
    SIEMPRE por nombre de encabezado.
  * Hay hojas que no son datos (GRAFICA, '..') y los libros son acumulativos (repiten meses anteriores).
  * El TÍTULO del boletín está en celdas combinadas (solo la primera celda trae el texto).
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.services.exporter import COLUMNAS

ALIAS = {"PRECIO": "COSTO"}
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
MAX_FILAS_ENCABEZADO = 15
ANIO_DEFECTO = 2026


def _norm(txt: Any) -> str:
    return re.sub(r"\s+", " ", str(txt or "")).strip().upper()


_CANON = {_norm(c): c for c in COLUMNAS}


@dataclass
class FilaCruda:
    archivo: str
    hoja: str
    fila: int
    ref: tuple[int, int] | None  # (año, mes) que el nombre del archivo/hoja sugiere
    hoja_propia: bool  # la hoja se llama como el mes del archivo (no es una copia acumulada)
    valores: dict[str, Any] = field(default_factory=dict)  # clave: nombre canónico de columna
    enlace: str | None = None  # destino del hipervínculo de la celda de evidencia (si lo hay)


def mes_de_referencia(archivo: str, hoja: str) -> tuple[tuple[int, int] | None, bool]:
    """(año, mes) según el nombre de la hoja y, si no, el del archivo. El bool indica si salió de la hoja."""
    for texto, de_hoja in ((hoja, True), (Path(archivo).stem.replace("_", " "), False)):
        palabras = re.findall(r"[a-záéíóú]+", texto.casefold())
        mes = next((MESES[p] for p in palabras if p in MESES), None)
        if mes:
            anio = re.search(r"20\d\d", texto)
            return (int(anio[0]) if anio else ANIO_DEFECTO, mes), de_hoja
    return None, False


def _fila_encabezado(ws: Worksheet) -> int | None:
    for r in range(1, MAX_FILAS_ENCABEZADO + 1):
        if _norm(ws.cell(r, 1).value).startswith("TÍTULO"):
            return r
    return None


def _titulos_combinados(ws: Worksheet, primera: int) -> dict[int, Any]:
    """{fila: texto} para las celdas combinadas de la columna A (el texto vive en la celda superior)."""
    rellenos: dict[int, Any] = {}
    for rango in ws.merged_cells.ranges:
        if rango.min_col == 1 and rango.max_col == 1 and rango.min_row >= primera:
            valor = ws.cell(rango.min_row, 1).value
            for r in range(rango.min_row, rango.max_row + 1):
                rellenos[r] = valor
    return rellenos


def leer_archivo(ruta: Path) -> Iterator[FilaCruda]:
    wb = load_workbook(ruta, data_only=True)
    for ws in wb.worksheets:
        hdr = _fila_encabezado(ws)
        if hdr is None:
            continue  # GRAFICA, '..', etc.
        cols: dict[str, int] = {}
        for c in range(1, ws.max_column + 1):
            nombre = _norm(ws.cell(hdr, c).value)
            canon = _CANON.get(ALIAS.get(nombre, nombre))
            if canon and canon not in cols:
                cols[canon] = c
        ref, de_hoja = mes_de_referencia(ruta.name, ws.title)
        combinados = _titulos_combinados(ws, hdr + 1)
        for r in range(hdr + 1, ws.max_row + 1):
            valores = {n: ws.cell(r, c).value for n, c in cols.items()}
            esenciales = ("TITULAR DEL MEDIO", "TÍTULO", "MEDIO", "EVIDENCIA DE LA NOTICIA (ENLACES)")
            if all(valores.get(k) in (None, "") for k in esenciales):
                continue  # fila vacía (la plantilla trae cientos con formato)
            if r in combinados and valores.get("TÍTULO") in (None, ""):
                valores["TÍTULO"] = combinados[r]
            enlace = None
            if "EVIDENCIA DE LA NOTICIA (ENLACES)" in cols:
                h = ws.cell(r, cols["EVIDENCIA DE LA NOTICIA (ENLACES)"]).hyperlink
                enlace = getattr(h, "target", None)
            yield FilaCruda(ruta.name, ws.title, r, ref, de_hoja, valores, enlace)
