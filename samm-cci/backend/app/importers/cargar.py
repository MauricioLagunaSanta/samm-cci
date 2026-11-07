"""Carga del histórico: normaliza, quita duplicados entre hojas/archivos y guarda de forma idempotente."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.relevance import normalize
from app.extraction.url_tools import canonicalize_url, domain_of
from app.importers import normalizar as nz
from app.importers.excel_historico import FilaCruda, leer_archivo
from app.importers.reporte import Reporte
from app.models import Boletin, EstadoRelevancia, FuenteOrigen, Mencion, Sentimiento, TipoRegistro
from app.services.pipeline import COLOMBIA

UMBRAL_BOLETIN = 90  # similitud de títulos para considerar que dos filas hablan del mismo boletín
SIN_ENLACE = "(sin enlace)"


@dataclass
class FilaNormalizada:
    origen: FilaCruda
    titulo_boletin: str | None
    tipo: TipoRegistro | None
    titular: str | None
    medio: str | None
    fecha: date | None
    url: str  # enlace http o el texto original / SIN_ENLACE
    url_http: bool
    tipo_contenido: str | None
    redes: str | None
    sentimiento: Sentimiento | None
    observaciones: str | None
    clave: str = ""  # url canónica (o huella si no hay enlace): clave de deduplicación
    notas: list[str] = field(default_factory=list)

    @property
    def completitud(self) -> int:
        campos = (self.titulo_boletin, self.tipo, self.titular, self.medio, self.fecha, self.tipo_contenido,
                  self.redes, self.sentimiento, self.observaciones, self.url_http or None)
        return sum(c is not None for c in campos)


def _url(fila: FilaCruda) -> tuple[str, bool]:
    for candidato in (fila.valores.get("EVIDENCIA DE LA NOTICIA (ENLACES)"), fila.enlace):
        t = nz.limpiar_texto(candidato)
        if t and t.lower().startswith("http"):
            return t.split()[0], True
    t = nz.limpiar_texto(fila.valores.get("EVIDENCIA DE LA NOTICIA (ENLACES)"))
    return (t or SIN_ENLACE), False


def normalizar_fila(fila: FilaCruda) -> FilaNormalizada:
    v = fila.valores
    titulo = nz.limpiar_texto(v.get("TÍTULO"))
    titular = nz.limpiar_texto(v.get("TITULAR DEL MEDIO"))
    medio = nz.limpiar_texto(v.get("MEDIO"))
    tipo = nz.parse_tipo(v.get("TIPO"))
    fecha, nota_fecha = nz.parse_fecha(v.get("FECHA DE PUBLICACIÓN"), fila.ref)
    sentimiento, nota_sent = nz.parse_sentimiento(v.get("MENCIÓN POSITIVA"), v.get("MENCIÓN NEGATIVA"))
    url, url_http = _url(fila)
    n = FilaNormalizada(
        origen=fila,
        titulo_boletin=titulo if tipo == TipoRegistro.REPLICA else None,
        tipo=tipo,
        titular=titular or titulo,  # en las plantillas viejas el titular vive en TÍTULO
        medio=medio,
        fecha=fecha,
        url=url,
        url_http=url_http,
        tipo_contenido=nz.limpiar_texto(v.get("TIPO DE CONTENIDO")),
        redes=nz.redes_marcadas(v),
        sentimiento=sentimiento,
        observaciones=nz.limpiar_texto(v.get("OBSERVACIONES")),
    )
    if url_http:
        n.clave = canonicalize_url(url)
    else:
        base = f"{(medio or '').casefold()}|{normalize(n.titular or '')}|{fecha}"
        n.clave = "sin-enlace://" + hashlib.sha1(base.encode()).hexdigest()[:20]  # noqa: S324
    for nota in (nota_fecha, nota_sent):
        if nota:
            n.notas.append(nota)
    return n


def _registrar_anomalias(n: FilaNormalizada, rep: Reporte) -> None:
    f = n.origen
    if n.tipo is None:
        rep.anomalia(f, "tipo_vacio", "TIPO sin Mención/Réplica; queda 'Sin clasificar'")
    if not n.url_http:
        rep.anomalia(f, "sin_enlace", f"evidencia: {n.url[:60]}")
    if not n.titular:
        rep.anomalia(f, "sin_titular")
    if n.tipo == TipoRegistro.REPLICA and not n.titulo_boletin:
        rep.anomalia(f, "replica_sin_boletin", "Réplica sin TÍTULO de boletín")
    for nota in n.notas:
        if nota.startswith("año corregido"):
            rep.anomalia(f, "fecha_reparada", nota)
        elif nota.startswith("sin fecha") or nota.startswith("fecha ilegible"):
            rep.anomalia(f, "sin_fecha", nota)
        else:
            rep.anomalia(f, "sentimiento_ambiguo", nota)


def _elegir(candidatas: list[FilaNormalizada]) -> FilaNormalizada:
    """La versión con más campos llenos; en empate, la de una hoja propia del mes y luego la más reciente."""
    return max(candidatas, key=lambda n: (n.completitud, n.origen.hoja_propia, n.origen.archivo, n.origen.fila))


class _Boletines:
    """Get-or-create de boletines por título (coincidencia exacta o muy parecida)."""

    def __init__(self, session: Session):
        self.session = session
        self.lista: list[tuple[str, Boletin]] = [(normalize(b.titular), b) for b in session.scalars(select(Boletin))]
        self.creados = 0

    def obtener(self, titulo: str, fecha: date) -> Boletin:
        clave = normalize(titulo)
        for k, b in self.lista:
            if k == clave or fuzz.token_sort_ratio(k, clave) >= UMBRAL_BOLETIN:
                if fecha < b.fecha_envio:
                    b.fecha_envio = fecha  # el boletín salió el día de la primera réplica
                return b
        b = Boletin(titular=titulo[:500], texto="", fecha_envio=fecha)
        self.session.add(b)
        self.session.flush()
        self.lista.append((clave, b))
        self.creados += 1
        return b


def _fecha_publicacion(d: date) -> datetime:
    return datetime.combine(d, time(12, 0), tzinfo=COLOMBIA).astimezone(UTC)  # mediodía: no cambia de día


def importar(session: Session, rutas: Iterable[Path], *, dry_run: bool = False) -> Reporte:
    rep = Reporte(dry_run=dry_run)
    rutas = list(rutas)
    rep.archivos = len(rutas)

    por_clave: dict[str, list[FilaNormalizada]] = {}
    for ruta in rutas:
        for cruda in leer_archivo(ruta):
            rep.filas_leidas += 1
            n = normalizar_fila(cruda)
            por_clave.setdefault(n.clave, []).append(n)

    ganadoras: list[FilaNormalizada] = []
    for candidatas in por_clave.values():
        ganadora = _elegir(candidatas)
        rep.duplicados_descartados += len(candidatas) - 1
        ganadoras.append(ganadora)
        _registrar_anomalias(ganadora, rep)

    existentes = set(session.scalars(select(Mencion.url_canonica)))
    boletines = _Boletines(session)
    ganadoras.sort(key=lambda n: (n.fecha or date.max, n.origen.archivo, n.origen.fila))  # boletín: 1ª réplica
    ahora = datetime.now(UTC)
    for n in ganadoras:
        if n.clave in existentes:
            rep.ya_existentes += 1
            continue
        ref = n.origen.ref
        dia = n.fecha or (date(ref[0], ref[1], 1) if ref else date.today())
        boletin = boletines.obtener(n.titulo_boletin, dia) if n.titulo_boletin else None
        dominio = domain_of(n.url) if n.url_http else None
        medio = n.medio or dominio
        session.add(
            Mencion(
                titular=(n.titular or "(sin titular)")[:500],
                url=n.url,
                url_canonica=n.clave[:1000],
                url_resuelta=n.url_http,
                medio=medio[:200] if medio else None,
                dominio=dominio,
                fecha_publicacion=_fecha_publicacion(n.fecha) if n.fecha else None,
                fecha_monitoreo=dia,
                origen=FuenteOrigen.HISTORICO,
                estado_relevancia=EstadoRelevancia.VALIDA,
                via_relevancia="historico",
                motivo_relevancia="Etiquetada por una persona en el Excel mensual",
                fecha_validacion=ahora,
                tipo=n.tipo or TipoRegistro.SIN_CLASIFICAR,
                boletin_id=boletin.id if boletin else None,
                sentimiento=n.sentimiento,
                tipo_contenido=n.tipo_contenido and n.tipo_contenido[:120],
                redes=n.redes,
                observaciones=n.observaciones,
                archivo_origen=f"{n.origen.archivo}#{n.origen.hoja}!{n.origen.fila}"[:200],
            )
        )
        rep.importadas += 1
        rep.por_tipo[(n.tipo or TipoRegistro.SIN_CLASIFICAR).value] += 1
        rep.por_mes[f"{dia.year}-{dia.month:02d}"] += 1
    rep.boletines_creados = boletines.creados
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return rep


def listar_excel(ruta: Path) -> list[Path]:
    """Un archivo, o todos los .xlsx de una carpeta (ignora los temporales '~$...' de Excel)."""
    if ruta.is_dir():
        return sorted(p for p in ruta.glob("*.xlsx") if not p.name.startswith("~$"))
    return [ruta]
