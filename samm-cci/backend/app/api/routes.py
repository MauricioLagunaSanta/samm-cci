"""Rutas HTTP que consume el dashboard."""
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.config import get_settings, load_sources
from app.database import get_session
from app.services import metrics
from app.services.exporter import PlantillaInvalida, exportar_xlsx
from app.services.periodos import parse_mes

router = APIRouter(prefix="/api")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MES_QUERY = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mes en formato AAAA-MM")


NOMBRE_EXPORT = re.compile(r"^Monitoreo_de_Medios_(\d{4}-(?:0[1-9]|1[0-2]))_(\d{8}-\d{6})_(\d+)f\.xlsx$")


def get_exports_dir() -> Path:
    return get_settings().exports_dir


def get_config() -> dict:
    return load_sources()  # se relee en cada petición: editar sources.yaml no exige reiniciar


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/meses")
def meses(session: Session = Depends(get_session)) -> list[str]:
    """Meses con datos, del más reciente al más antiguo."""
    return metrics.meses_disponibles(session)


@router.get("/metricas/mensual")
def mensual(
    ultimos: int = Query(12, ge=1, le=36),
    hasta: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    session: Session = Depends(get_session),
    config: dict = Depends(get_config),
) -> dict:
    return metrics.metricas_mensuales(session, config, ultimos, hasta)


@router.get("/metricas/semanal")
def semanal(mes: str = MES_QUERY, session: Session = Depends(get_session), config: dict = Depends(get_config)) -> dict:
    return metrics.metricas_semanales(session, config, *parse_mes(mes))


@router.get("/resumen")
def resumen(mes: str = MES_QUERY, session: Session = Depends(get_session), config: dict = Depends(get_config)) -> dict:
    return metrics.resumen_mes(session, config, *parse_mes(mes))


@router.get("/menciones")
def menciones(
    mes: str = MES_QUERY, session: Session = Depends(get_session), config: dict = Depends(get_config)
) -> list[dict]:
    return metrics.menciones_del_mes(session, config, *parse_mes(mes))


@router.get("/export/xlsx")
def exportar(
    mes: str = MES_QUERY,
    session: Session = Depends(get_session),
    config: dict = Depends(get_config),
    exports_dir: Path = Depends(get_exports_dir),
) -> Response:
    """Genera el Excel del mes, lo devuelve y guarda una copia en la carpeta de exportaciones."""
    anio, num = parse_mes(mes)
    buffer = BytesIO()
    try:
        r = exportar_xlsx(session, config, anio, num, buffer, plantilla=get_settings().plantilla_xlsx)
    except PlantillaInvalida as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    contenido = buffer.getvalue()
    guardado = None
    try:
        exports_dir.mkdir(parents=True, exist_ok=True)
        guardado = f"Monitoreo_de_Medios_{mes}_{datetime.now():%Y%m%d-%H%M%S}_{r.filas}f.xlsx"
        (exports_dir / guardado).write_bytes(contenido)
    except OSError:
        guardado = None  # no guardar la copia no debe impedir la descarga
    headers = {
        "Content-Disposition": f'attachment; filename="Monitoreo_de_Medios_{mes}.xlsx"',
        "X-Filas": str(r.filas),
        "X-Por-Revisar": str(r.por_revisar),
    }
    if guardado:
        headers["X-Archivo-Guardado"] = guardado
    return Response(content=contenido, media_type=XLSX_MIME, headers=headers)


@router.get("/exportaciones")
def listar_exportaciones(exports_dir: Path = Depends(get_exports_dir)) -> list[dict]:
    """Excel generados anteriormente, del más reciente al más antiguo."""
    if not exports_dir.is_dir():
        return []
    salida = []
    for ruta in exports_dir.glob("*.xlsx"):
        m = NOMBRE_EXPORT.match(ruta.name)
        if not m:
            continue
        salida.append({
            "nombre": ruta.name,
            "mes": m.group(1),
            "generado": datetime.strptime(m.group(2), "%Y%m%d-%H%M%S").isoformat(timespec="seconds"),
            "filas": int(m.group(3)),
            "bytes": ruta.stat().st_size,
        })
    return sorted(salida, key=lambda e: e["generado"], reverse=True)


@router.get("/exportaciones/{nombre}")
def descargar_exportacion(nombre: str, exports_dir: Path = Depends(get_exports_dir)) -> Response:
    """Re-descarga un Excel guardado. Solo acepta nombres con el patrón generado por el sistema."""
    if not NOMBRE_EXPORT.match(nombre):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    ruta = exports_dir / nombre
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return Response(
        content=ruta.read_bytes(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
