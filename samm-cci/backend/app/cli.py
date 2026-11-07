"""Línea de comandos del backend.

    python -m app.cli init-db                 # crea las tablas
    python -m app.cli extract [--sin-validar] # busca notas nuevas y valida su relevancia
    python -m app.cli validate [--limit N]    # valida las notas pendientes (descarga el cuerpo)
    python -m app.cli revalidar               # reaplica las reglas sin red (tras editar sources.yaml)
    python -m app.cli listar [--fecha AAAA-MM-DD] [--estado Válida|Descartada|Revisar|Pendiente]
    python -m app.cli exportar [--mes AAAA-MM] [--salida ruta.xlsx] [--plantilla original.xlsx]
    python -m app.cli importar CARPETA_O_ARCHIVO [--dry-run] [--reporte anomalias.csv]
    python -m app.cli evaluar [--mes AAAA-MM]   # acierto del clasificador vs. las etiquetas del histórico
"""
import argparse
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings, load_sources
from app.database import SessionLocal, init_db
from app.importers.cargar import importar, listar_excel
from app.models import EstadoRelevancia, Mencion
from app.services.evaluacion import evaluar
from app.services.exporter import PlantillaInvalida, exportar_xlsx
from app.services.periodos import mes_str, parse_mes
from app.services.pipeline import hoy_colombia, run_pipeline
from app.services.validation import revalidar, validate_pending


def _fmt(conteo) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(conteo.items())) or "nada que procesar"


def cmd_extract(args) -> int:
    init_db()
    config = load_sources()
    with SessionLocal() as session:
        ej = run_pipeline(session, config)
        print(
            f"Ejecución #{ej.id} [{ej.estado.value}] consultas={ej.consultas} "
            f"encontrados={ej.encontrados} nuevos={ej.nuevos} "
            f"duplicados={ej.duplicados} descartados={ej.descartados}"
        )
        if ej.errores:
            print("Errores:\n" + ej.errores, file=sys.stderr)
        if not args.sin_validar:
            print("Validando relevancia (descarga el cuerpo de cada nota)...")
            print("Resultado:", _fmt(validate_pending(session, config)))
    return 0 if ej.estado.value != "error" else 1


def cmd_validate(args) -> int:
    init_db()
    with SessionLocal() as session:
        print("Resultado:", _fmt(validate_pending(session, load_sources(), limit=args.limit)))
    return 0


def cmd_revalidar(_args) -> int:
    init_db()
    with SessionLocal() as session:
        print("Resultado:", _fmt(revalidar(session, load_sources())))
    return 0


def cmd_listar(args) -> int:
    init_db()
    dia = date.fromisoformat(args.fecha) if args.fecha else hoy_colombia()
    stmt = select(Mencion).where(Mencion.fecha_monitoreo == dia).order_by(Mencion.id)
    if args.estado:
        stmt = stmt.where(Mencion.estado_relevancia == EstadoRelevancia(args.estado))
    with SessionLocal() as session:
        filas = session.scalars(stmt).all()
        print(f"{len(filas)} registros del {dia.isoformat()}")
        for m in filas:
            url_ok = "URL real" if m.url_resuelta else "URL sin resolver"
            cuerpo = "cuerpo OK" if m.cuerpo_ok else f"sin cuerpo ({m.error_cuerpo or 'no descargado'})"
            print(f"- [{m.estado_relevancia.value}] {m.medio or m.dominio or '?'} | {m.titular}")
            print(f"  {m.url}\n  {url_ok} · {cuerpo} · consulta: {m.consulta}")
            if m.motivo_relevancia:
                print(f"  motivo: {m.motivo_relevancia} -> {m.terminos_detectados or '-'}")
    return 0


def cmd_exportar(args) -> int:
    init_db()
    hoy = hoy_colombia()
    try:
        anio, mes = parse_mes(args.mes) if args.mes else (hoy.year, hoy.month)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    nombre = f"Monitoreo_de_Medios_{mes_str(anio, mes)}.xlsx"
    salida = Path(args.salida) if args.salida else Path("data/exports") / nombre
    salida.parent.mkdir(parents=True, exist_ok=True)
    plantilla = args.plantilla or get_settings().plantilla_xlsx
    with SessionLocal() as session:
        try:
            r = exportar_xlsx(session, load_sources(), anio, mes, salida, plantilla=plantilla)
        except PlantillaInvalida as exc:
            print(exc, file=sys.stderr)
            return 1
    print(f"Excel generado: {salida.resolve()}")
    print(f"  {r.filas} filas ({r.menciones} menciones, {r.replicas} réplicas) · modo: "
          f"{'plantilla ' + str(plantilla) if plantilla else 'desde cero'}")
    if r.por_revisar:
        print(f"  Atención: {r.por_revisar} notas del mes están en 'Revisar' y NO se incluyeron.")
    if r.sin_url_real:
        print(f"  Atención: {r.sin_url_real} filas aún tienen enlace de Google News (URL sin resolver).")
    return 0


def cmd_importar(args) -> int:
    ruta = Path(args.ruta)
    if not ruta.exists():
        print(f"No existe: {ruta}", file=sys.stderr)
        return 2
    archivos = listar_excel(ruta)
    if not archivos:
        print("No se encontraron archivos .xlsx", file=sys.stderr)
        return 2
    init_db()
    with SessionLocal() as session:
        rep = importar(session, archivos, dry_run=args.dry_run)
    print(rep.texto())
    if args.reporte:
        rep.a_csv(Path(args.reporte))
        print(f"  Detalle de anomalías: {Path(args.reporte).resolve()}")
    return 0


def cmd_evaluar(args) -> int:
    init_db()
    try:
        mes = parse_mes(args.mes) if args.mes else None
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    with SessionLocal() as session:
        ev = evaluar(session, load_sources(), mes)
    if not ev.tipo.total:
        print("No hay histórico importado. Ejecuta primero: python -m app.cli importar <carpeta>")
        return 1
    print(ev.texto())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="samm")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(func=lambda _a: (init_db(), print("OK"), 0)[2])
    p = sub.add_parser("extract")
    p.add_argument("--sin-validar", action="store_true")
    p.set_defaults(func=cmd_extract)
    p = sub.add_parser("validate")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_validate)
    sub.add_parser("revalidar").set_defaults(func=cmd_revalidar)
    p = sub.add_parser("listar")
    p.add_argument("--fecha")
    p.add_argument("--estado", choices=[e.value for e in EstadoRelevancia])
    p.set_defaults(func=cmd_listar)
    p = sub.add_parser("exportar")
    p.add_argument("--mes", help="AAAA-MM (por defecto, el mes actual)")
    p.add_argument("--salida")
    p.add_argument("--plantilla", help="Excel original de Monitoreo de Medios para conservar su formato")
    p.set_defaults(func=cmd_exportar)
    p = sub.add_parser("importar", help="Importa los Excel mensuales hechos a mano (histórico)")
    p.add_argument("ruta", help="Carpeta con los .xlsx o un archivo")
    p.add_argument("--dry-run", action="store_true", help="Simula: muestra el reporte sin guardar nada")
    p.add_argument("--reporte", help="CSV donde guardar cada anomalía (archivo, hoja, fila, detalle)")
    p.set_defaults(func=cmd_importar)
    p = sub.add_parser("evaluar", help="Acierto del clasificador contra el histórico etiquetado")
    p.add_argument("--mes", help="AAAA-MM (por defecto, todos)")
    p.set_defaults(func=cmd_evaluar)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
