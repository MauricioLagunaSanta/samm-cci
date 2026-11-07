"""Exportador de la plantilla mensual "Monitoreo de Medios" (formato CM-F-005, 27 columnas).

Estructura REAL de los archivos de la CCI: filas 1-3 = bloque corporativo (título, código, versión),
encabezados en la fila 4 y datos desde la 5.

Dos modos:
  * Desde cero (por defecto): replica ese bloque corporativo y escribe los 27 encabezados en la fila 4.
  * Con plantilla (`plantilla=...` o PLANTILLA_XLSX en .env): abre TU archivo real, verifica los encabezados
    y agrega las filas conservando formatos, anchos y las filas 1-3 intactas.

Convenciones del archivo manual que se respetan:
  * MENCIÓN POSITIVA / MENCIÓN NEGATIVA llevan el nombre del medio en mayúsculas (no una "X").
  * FACEBOOK / INSTAGRAM / X / LINKEDIN se marcan con "X" (la importación acepta cualquier texto).
  * TOTAL PUBLICACIONES se deja vacío; COSTO, PAGA y los comentarios los completa la persona.
"""
from __future__ import annotations

import re
from collections import Counter
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.classification.provisional import UMBRAL_DEFECTO, clasificar, tipo_efectivo
from app.extraction.url_tools import is_google_news_link
from app.models import FuenteOrigen, Mencion, Sentimiento, TipoRegistro
from app.services.periodos import fecha_local, revisar_por_mes, validas_por_mes

FILA_ENCABEZADO = 4
PRIMERA_FILA_DATOS = FILA_ENCABEZADO + 1

COLUMNAS: list[str] = [
    "TÍTULO",
    "TIPO",
    "No MEDIOS QUE REPLICAN EL BOLETIN",
    "TITULAR DEL MEDIO",
    "MEDIO",
    "COSTO",
    "FECHA DE PUBLICACIÓN",
    "PÁGINA WEB",
    "EVIDENCIA DE LA NOTICIA (ENLACES)",
    "PAGA",
    "TIPO DE CONTENIDO",
    "FACEBOOK",
    "INSTAGRAM",
    "X",
    "LINKEDIN",
    "TOTAL PUBLICACIONES",
    "N° COMENTARIOS",
    "EVIDENCIA DEL COMENTARIO (ENLACE)",
    "CANT. COMENTARIOS POSITIVOS",
    "RED SOCIAL DONDE SE REALIZAN LOS COMENTARIOS POSITIVOS",
    "CANT. COMENTARIOS NEGATIVOS",
    "ENLACE DE LA PUBLICACIÓN",
    "RED SOCIAL DONDE SE REALIZAN LOS COMENTARIOS NEGATIVOS",
    "PERSONA HACÍA QUIEN SE GENERA EL COMENTARIO",
    "MENCIÓN POSITIVA",
    "MENCIÓN NEGATIVA",
    "OBSERVACIONES",
]
assert len(COLUMNAS) == 27

_IDX = {nombre: i + 1 for i, nombre in enumerate(COLUMNAS)}  # nombre -> número de columna (1-based)
_ANCHOS = {
    "TÍTULO": 34, "TIPO": 11, "No MEDIOS QUE REPLICAN EL BOLETIN": 14, "TITULAR DEL MEDIO": 55,
    "MEDIO": 22, "FECHA DE PUBLICACIÓN": 14, "PÁGINA WEB": 9, "EVIDENCIA DE LA NOTICIA (ENLACES)": 48,
    "MENCIÓN POSITIVA": 11, "MENCIÓN NEGATIVA": 11, "OBSERVACIONES": 60,
}
_ANCHO_DEFECTO = 14


class PlantillaInvalida(ValueError):
    """La plantilla indicada no tiene los 27 encabezados esperados en la fila 4."""


@dataclass
class ResumenExport:
    anio: int
    mes: int
    filas: int
    menciones: int
    replicas: int
    por_revisar: int  # notas en estado "Revisar" del mes: NO se exportan, requieren decisión humana
    sin_url_real: int  # filas cuya evidencia sigue siendo un enlace de Google News
    destino: str


def _norm_enc(txt) -> str:
    t = re.sub(r"\s+", " ", str(txt or "")).strip().casefold()
    return "costo" if t == "precio" else t  # febrero llama PRECIO a la columna COSTO


def _observaciones(m: Mencion, info) -> str:
    notas: list[str] = []
    if m.origen == FuenteOrigen.HISTORICO:
        return m.observaciones or ""
    if info.tipo == TipoRegistro.REPLICA and m.boletin_id is None:
        notas.append(f"Réplica provisional: titular similar en {info.n_medios} medios; boletín sin identificar")
    if m.via_relevancia == "evento":
        notas.append(f"Relevante por evento ({m.terminos_detectados}); la nota no cita a la CCI")
    elif m.via_relevancia == "entidad_debil":
        notas.append("Dice 'Cámara de Comercio'/'CCI' con contexto de Ibagué/Tolima; confirmar que es la CCI")
    if is_google_news_link(m.url):
        notas.append("URL de Google News sin resolver; reemplazar por la URL del medio")
    return "; ".join(notas)


def filas_del_mes(session: Session, config: dict, anio: int, mes: int) -> list[dict]:
    """Notas Válidas del mes convertidas a filas con las 27 columnas, listas para escribir."""
    notas = validas_por_mes(session).get((anio, mes), [])
    umbral = int(config.get("clasificacion_provisional", {}).get("umbral_titular", UMBRAL_DEFECTO))
    info = clasificar(notas, umbral)

    # Réplicas agrupadas (por boletín o grupo provisional, de la más antigua a la más reciente) y luego menciones
    def orden(m: Mencion):
        i = info[m.id]
        es_replica = tipo_efectivo(m, i) == TipoRegistro.REPLICA
        grupo = (0, m.boletin_id) if m.boletin_id else (1, i.grupo or 0)
        return (0 if es_replica else 1, grupo, fecha_local(m), m.id)

    por_boletin = Counter(m.boletin_id for m in notas if m.boletin_id)
    vistos: set[int] = set()
    filas: list[dict] = []
    for m in sorted(notas, key=orden):
        i = info[m.id]
        tipo = tipo_efectivo(m, i)
        fila = dict.fromkeys(COLUMNAS)
        fila["TÍTULO"] = m.boletin.titular if m.boletin else None
        fila["TIPO"] = tipo.value
        if tipo == TipoRegistro.REPLICA:
            if m.boletin_id:
                if m.boletin_id not in vistos:  # una vez por grupo: no infla sumas
                    fila["No MEDIOS QUE REPLICAN EL BOLETIN"] = por_boletin[m.boletin_id]
                    vistos.add(m.boletin_id)
            elif i.primera_del_grupo:
                fila["No MEDIOS QUE REPLICAN EL BOLETIN"] = i.n_medios
        fila["TITULAR DEL MEDIO"] = m.titular
        fila["MEDIO"] = m.medio or m.dominio
        fila["FECHA DE PUBLICACIÓN"] = fecha_local(m)
        contenido = m.tipo_contenido or "PÁGINA WEB"
        fila["TIPO DE CONTENIDO"] = contenido
        if contenido.upper() in ("PÁGINA WEB", "PAGINA WEB", "WEB"):
            fila["PÁGINA WEB"] = "X"
        for red in (m.redes or "").split(","):
            if red in fila:
                fila[red] = "X"  # estandariza: el importador acepta cualquier texto, el exportador escribe "X"
        fila["EVIDENCIA DE LA NOTICIA (ENLACES)"] = m.url
        etiqueta = (m.medio or m.dominio or "").upper() or "X"  # la marca de sentimiento es el nombre del medio
        fila["MENCIÓN POSITIVA"] = etiqueta if i.sentimiento == Sentimiento.POSITIVO else None
        fila["MENCIÓN NEGATIVA"] = etiqueta if i.sentimiento == Sentimiento.NEGATIVO else None
        fila["OBSERVACIONES"] = _observaciones(m, i) or None
        filas.append(fila)
    return filas


def construir_dataframe(filas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=COLUMNAS, dtype=object)


# ---------------------------------------------------------------- escritura


def _bloque_corporativo(ws, anio: int, mes: int) -> None:
    """Filas 1-3 como en los archivos reales: logo (A:C), título (D:Z) y código/versión/página (AA)."""
    ultima = get_column_letter(len(COLUMNAS))
    ws.merge_cells("A1:C3")
    ws.merge_cells(f"D1:{get_column_letter(len(COLUMNAS) - 1)}3")
    ws["D1"] = "MONITOREO MEDIOS DE COMUNICACIÓN"
    ws["D1"].font = Font(bold=True, size=16)
    ws["D1"].alignment = Alignment(horizontal="center", vertical="center")
    ws[f"{ultima}1"] = "Código: CM-F-005"
    ws[f"{ultima}2"] = "Ver: 02 - 17/Diciembre/2024"
    ws[f"{ultima}3"] = "Página 1 de 1"
    for fila in (1, 2, 3):
        ws[f"{ultima}{fila}"].font = Font(size=9)
        ws.row_dimensions[fila].height = 18


def _escribir_desde_cero(df: pd.DataFrame, destino, anio: int, mes: int) -> None:
    with pd.ExcelWriter(destino, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="CM-F-005", startrow=FILA_ENCABEZADO - 1, index=False)
        ws = writer.sheets["CM-F-005"]
        _bloque_corporativo(ws, anio, mes)

        borde = Border(bottom=Side(style="thin", color="999999"))
        for col in range(1, len(COLUMNAS) + 1):
            c = ws.cell(row=FILA_ENCABEZADO, column=col)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
            c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
            c.border = borde
            ws.column_dimensions[get_column_letter(col)].width = _ANCHOS.get(COLUMNAS[col - 1], _ANCHO_DEFECTO)
        ws.row_dimensions[FILA_ENCABEZADO].height = 45

        ultima = FILA_ENCABEZADO + len(df)
        for fila in range(PRIMERA_FILA_DATOS, ultima + 1):
            ws.cell(row=fila, column=_IDX["FECHA DE PUBLICACIÓN"]).number_format = "dd/mm/yyyy"
            for nombre in ("TITULAR DEL MEDIO", "OBSERVACIONES"):
                ws.cell(row=fila, column=_IDX[nombre]).alignment = Alignment(wrap_text=True, vertical="top")
            for nombre in ("TIPO", "PÁGINA WEB", "FACEBOOK", "INSTAGRAM", "X", "LINKEDIN"):
                ws.cell(row=fila, column=_IDX[nombre]).alignment = Alignment(horizontal="center", vertical="top")
        _enlaces(ws, PRIMERA_FILA_DATOS, ultima)
        ws.freeze_panes = ws.cell(row=PRIMERA_FILA_DATOS, column=1)
        ws.auto_filter.ref = f"A{FILA_ENCABEZADO}:{get_column_letter(len(COLUMNAS))}{max(ultima, FILA_ENCABEZADO)}"


def _enlaces(ws, desde: int, hasta: int) -> None:
    col = _IDX["EVIDENCIA DE LA NOTICIA (ENLACES)"]
    for fila in range(desde, hasta + 1):
        c = ws.cell(row=fila, column=col)
        if c.value and str(c.value).lower().startswith("http"):
            c.hyperlink = str(c.value)
            c.font = Font(color="0563C1", underline="single")


def _escribir_en_plantilla(filas: list[dict], destino, plantilla: Path) -> None:
    wb = load_workbook(plantilla)
    ws = wb["CM-F-005"] if "CM-F-005" in wb.sheetnames else wb.active

    encontrados = [ws.cell(row=FILA_ENCABEZADO, column=c).value for c in range(1, len(COLUMNAS) + 1)]
    distintos = [
        f"col {i + 1}: esperaba '{esp}', hay '{enc}'"
        for i, (esp, enc) in enumerate(zip(COLUMNAS, encontrados, strict=True))
        if _norm_enc(esp) != _norm_enc(enc)
    ]
    if distintos:
        raise PlantillaInvalida(
            f"La plantilla '{plantilla.name}' no coincide con los 27 encabezados de la fila "
            f"{FILA_ENCABEZADO}:\n  " + "\n  ".join(distintos[:8])
        )

    # Primera fila libre: sin titular ni tipo
    fila = PRIMERA_FILA_DATOS
    while ws.cell(row=fila, column=_IDX["TITULAR DEL MEDIO"]).value or ws.cell(row=fila, column=_IDX["TIPO"]).value:
        fila += 1
    primera_libre = fila
    estilos = [copy(ws.cell(row=PRIMERA_FILA_DATOS, column=c)._style) for c in range(1, len(COLUMNAS) + 1)]

    for datos in filas:
        for nombre, valor in datos.items():
            c = ws.cell(row=fila, column=_IDX[nombre])
            if fila != PRIMERA_FILA_DATOS:
                c._style = copy(estilos[_IDX[nombre] - 1])  # hereda el formato de la primera fila de datos
            c.value = valor
            if nombre == "FECHA DE PUBLICACIÓN" and c.number_format == "General":
                c.number_format = "dd/mm/yyyy"
        fila += 1
    _enlaces(ws, primera_libre, fila - 1)
    wb.save(destino)


def exportar_xlsx(
    session: Session,
    config: dict,
    anio: int,
    mes: int,
    destino: str | Path | BinaryIO,
    plantilla: str | Path | None = None,
) -> ResumenExport:
    """Genera el Excel del mes en `destino` (ruta o buffer binario). Devuelve un resumen."""
    filas = filas_del_mes(session, config, anio, mes)
    if plantilla:
        _escribir_en_plantilla(filas, destino, Path(plantilla))
    else:
        _escribir_desde_cero(construir_dataframe(filas), destino, anio, mes)

    replicas = sum(f["TIPO"] == TipoRegistro.REPLICA.value for f in filas)
    return ResumenExport(
        anio=anio,
        mes=mes,
        filas=len(filas),
        menciones=len(filas) - replicas,
        replicas=replicas,
        por_revisar=len(revisar_por_mes(session).get((anio, mes), [])),
        sin_url_real=sum(is_google_news_link(f["EVIDENCIA DE LA NOTICIA (ENLACES)"] or "") for f in filas),
        destino=str(destino) if isinstance(destino, (str, Path)) else "<memoria>",
    )


__all__ = ["COLUMNAS", "PlantillaInvalida", "ResumenExport", "exportar_xlsx", "filas_del_mes"]
