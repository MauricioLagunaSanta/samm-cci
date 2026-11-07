"""Validación de relevancia: ¿la nota realmente habla de la CCI (o de un evento que apoya)?

Lógica pura, sin red ni base de datos, para poder probarla y medirla con un gold set.

Orden de decisión (la primera regla que aplica gana):
  1. Entidad fuerte  ("Cámara de Comercio de Ibagué", "@CamaraIbague", ...)  -> VÁLIDA (alta)
  2. Entidad débil   ("Cámara de Comercio" a secas o "CCI") con Ibagué/Tolima cerca -> VÁLIDA (media)
  3. Evento clave    ("Ibagué Negocios y Moda", "Cacao de Oro", ...)         -> VÁLIDA (vía evento)
  4. Entidad débil sin contexto local                                         -> REVISAR
  5. Nada, y se pudo leer el cuerpo                                           -> DESCARTADA
  6. Nada, pero no hay cuerpo (solo titular/resumen)                          -> REVISAR
Nunca se descarta una nota cuyo cuerpo no se pudo leer: eso destruiría el recall.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.models.enums import EstadoRelevancia

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_CCI_TOKEN = re.compile(r"\bCCI\b")  # sensible a mayúsculas: "cci" en minúscula no es la sigla
_OTHER_CHAMBER = re.compile(r"^ (?:de la|de los|de las|del|de|para) (\w+)")


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, signos ni dobles espacios. 'Ibagué,' -> 'ibague'."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", text).strip()


def _find(phrase: str, text: str) -> list[int]:
    """Posiciones de una frase normalizada como palabra(s) completa(s) en texto normalizado."""
    return [m.start() for m in re.finditer(rf"\b{re.escape(phrase)}\b", text)]


@dataclass(frozen=True)
class Reglas:
    entidad_fuerte: tuple[str, ...]
    contexto_local: tuple[str, ...]
    ventana: int
    eventos: tuple[tuple[str, tuple[str, ...]], ...]  # (nombre, frases normalizadas)


def compilar_reglas(config: dict) -> Reglas:
    rel = config.get("relevancia", {})
    eventos = []
    for ev in config.get("eventos", []):
        frases = tuple(dict.fromkeys(normalize(x) for x in [ev["nombre"], *ev.get("alias", [])]))
        eventos.append((ev["nombre"], frases))
    return Reglas(
        entidad_fuerte=tuple(normalize(x) for x in rel.get("entidad_fuerte", [])),
        contexto_local=tuple(normalize(x) for x in rel.get("contexto_local", ["ibague", "tolima"])),
        ventana=int(rel.get("ventana_contexto", 300)),
        eventos=tuple(eventos),
    )


@dataclass(frozen=True)
class Resultado:
    estado: EstadoRelevancia
    via: str | None
    motivo: str
    terminos: tuple[str, ...] = field(default_factory=tuple)


def _tiene_contexto(texto_norm: str, ini: int, fin: int, reglas: Reglas) -> bool:
    ventana = texto_norm[max(0, ini - reglas.ventana) : fin + reglas.ventana]
    return any(_find(t, ventana) for t in reglas.contexto_local)


def _entidad_debil(texto: str, texto_norm: str, reglas: Reglas) -> tuple[list[str], bool]:
    """Devuelve (coincidencias con contexto local, hubo_coincidencia_sin_contexto)."""
    con_contexto: list[str] = []
    sin_contexto = False
    frase = "camara de comercio"
    for pos in _find(frase, texto_norm):
        fin = pos + len(frase)
        otra = _OTHER_CHAMBER.match(texto_norm[fin : fin + 40])
        if otra and otra.group(1) not in reglas.contexto_local:
            continue  # "Cámara de Comercio de Bogotá/Cali/...": otra entidad
        if _tiene_contexto(texto_norm, pos, fin, reglas):
            con_contexto.append("Cámara de Comercio (con contexto local)")
        else:
            sin_contexto = True
    for m in _CCI_TOKEN.finditer(texto):
        # La ventana se toma sobre el texto original para conservar la sigla en mayúsculas
        ventana = normalize(texto[max(0, m.start() - reglas.ventana) : m.end() + reglas.ventana])
        if any(_find(t, ventana) for t in reglas.contexto_local):
            con_contexto.append("CCI (con contexto local)")
        else:
            sin_contexto = True
    return list(dict.fromkeys(con_contexto)), sin_contexto


def evaluar(
    titular: str,
    resumen: str | None,
    cuerpo: str | None,
    reglas: Reglas,
) -> Resultado:
    """Evalúa una nota. `cuerpo=None` significa que no se pudo leer el cuerpo."""
    texto = "\n".join(p for p in (titular, resumen, cuerpo) if p)
    texto_norm = normalize(texto)
    donde = "titular, resumen y cuerpo" if cuerpo else "solo titular y resumen (sin cuerpo)"

    fuertes = [f for f in reglas.entidad_fuerte if _find(f, texto_norm)]
    if fuertes:
        return Resultado(
            EstadoRelevancia.VALIDA, "entidad",
            f"Menciona a la CCI de forma directa ({donde})", tuple(fuertes),
        )

    debiles, hubo_sin_contexto = _entidad_debil(texto, texto_norm, reglas)
    if debiles:
        return Resultado(
            EstadoRelevancia.VALIDA, "entidad_debil",
            f"Menciona 'Cámara de Comercio'/'CCI' con contexto de Ibagué/Tolima ({donde})",
            tuple(debiles),
        )

    eventos = [nombre for nombre, frases in reglas.eventos if any(_find(f, texto_norm) for f in frases)]
    if eventos:
        return Resultado(
            EstadoRelevancia.VALIDA, "evento",
            f"Menciona un evento que apoya la CCI: {', '.join(eventos)} ({donde})", tuple(eventos),
        )

    if hubo_sin_contexto:
        return Resultado(
            EstadoRelevancia.REVISAR, "entidad_debil",
            "Menciona 'Cámara de Comercio'/'CCI' pero sin contexto de Ibagué/Tolima: puede ser otra entidad",
            ("Cámara de Comercio/CCI (sin contexto)",),
        )

    if cuerpo:
        return Resultado(
            EstadoRelevancia.DESCARTADA, None,
            "El cuerpo no menciona a la CCI ni a ningún evento clave",
        )
    return Resultado(
        EstadoRelevancia.REVISAR, None,
        "No se pudo leer el cuerpo y el titular/resumen no bastan para decidir",
    )
