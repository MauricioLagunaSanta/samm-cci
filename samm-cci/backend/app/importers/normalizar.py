"""Limpieza de los valores sucios de los Excel manuales: 'NA', fechas con año mal escrito, etc."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any

from openpyxl.utils.datetime import from_excel

from app.models import Sentimiento, TipoRegistro

_NA = {"", "na", "n/a", "n.a.", "n.a", "none", "null", "-", "--", "s/n", "nan"}
REDES = ("FACEBOOK", "INSTAGRAM", "X", "LINKEDIN")
ANIOS_PLAUSIBLES = range(2024, 2028)


def es_na(v: Any) -> bool:
    return v is None or str(v).strip().casefold() in _NA


def limpiar_texto(v: Any) -> str | None:
    """Texto sin 'NA', con espacios colapsados y letras 'matemáticas' (𝗖𝗮́𝗺𝗮𝗿𝗮) llevadas a normales."""
    if es_na(v):
        return None
    txt = unicodedata.normalize("NFKC", str(v))
    return re.sub(r"\s+", " ", txt).strip() or None


def _sin_tildes(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def parse_tipo(v: Any) -> TipoRegistro | None:
    clave = _sin_tildes(str(v or "")).strip().casefold()
    return {"mencion": TipoRegistro.MENCION, "replica": TipoRegistro.REPLICA}.get(clave)


def parse_sentimiento(positiva: Any, negativa: Any) -> tuple[Sentimiento | None, str | None]:
    """Positivo/Negativo si hay marca (cualquier texto: 'X' o el nombre del medio). Sin marca => None
    ('sin etiquetar'): en los archivos recientes la columna está vacía, no significa 'neutro'."""
    pos, neg = not es_na(positiva), not es_na(negativa)
    if pos and neg:
        return None, "marcada como positiva y negativa a la vez"
    if pos:
        return Sentimiento.POSITIVO, None
    if neg:
        return Sentimiento.NEGATIVO, None
    return None, None


def redes_marcadas(valores: dict[str, Any]) -> str | None:
    marcadas = [r for r in REDES if not es_na(valores.get(r))]
    return ",".join(marcadas) or None


def parse_fecha(v: Any, ref: tuple[int, int] | None) -> tuple[date | None, str | None]:
    """Convierte la celda a fecha y repara años mal escritos hacia el mes de referencia del archivo.
    Devuelve (fecha | None, nota | None); la nota describe la reparación o por qué no hay fecha."""
    if es_na(v):
        return None, "sin fecha de publicación"
    d: date | None = None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    elif isinstance(v, (int, float)) and 30000 < v < 80000:
        d = from_excel(v).date()
    elif isinstance(v, str):
        t = v.strip()
        m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", t)
        n = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", t)
        try:
            if m:
                d = date(int(m[3]), int(m[2]), int(m[1]))  # día/mes/año (formato colombiano)
            elif n:
                d = date(int(n[1]), int(n[2]), int(n[3]))
        except ValueError:
            d = None
    if d is None:
        return None, f"fecha ilegible: {str(v)[:30]!r}"
    return _reparar(d, ref)


def _con_anio(d: date, anio: int) -> date | None:
    try:
        return d.replace(year=anio)
    except ValueError:  # 29 de febrero
        return None


def _reparar(d: date, ref: tuple[int, int] | None) -> tuple[date, str | None]:
    if ref is None:
        return d, None
    inicio_ref = date(ref[0], ref[1], 1)
    if d.year not in ANIOS_PLAUSIBLES:  # 0206, 3036...: el año es un error de digitación
        arreglada = _con_anio(d, ref[0])
        if arreglada:
            return arreglada, f"año corregido {d.year}->{ref[0]}"
        return d, None
    # Año plausible pero muy atrasado respecto al archivo: solo se corrige si, cambiando el año,
    # cae dentro del mes del archivo (así NO se tocan las notas legítimas de meses anteriores)
    if (inicio_ref - d).days > 75:
        arreglada = _con_anio(d, ref[0])
        if arreglada and arreglada.year != d.year and (arreglada.year, arreglada.month) == ref:
            return arreglada, f"año corregido {d.year}->{ref[0]}"
    return d, None


def sumar_dias(d: date, n: int) -> date:  # utilidad pequeña para pruebas
    return d + timedelta(days=n)
