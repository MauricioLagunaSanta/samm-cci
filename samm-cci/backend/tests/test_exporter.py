from datetime import UTC, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.classification.provisional import clasificar, sentimiento_lexico
from app.models import EstadoRelevancia as E
from app.models import Sentimiento, TipoRegistro
from app.services.exporter import COLUMNAS, FILA_ENCABEZADO, PlantillaInvalida, exportar_xlsx
from app.services.periodos import fecha_local
from tests.conftest import crear_nota

CONFIG: dict = {}


def _exportar(db, **kw):
    buf = BytesIO()
    resumen = exportar_xlsx(db, CONFIG, 2026, 10, buf, **kw)
    return resumen, load_workbook(BytesIO(buf.getvalue()))


def _fila(ws, n):
    return {ws.cell(FILA_ENCABEZADO, c).value: ws.cell(n, c).value for c in range(1, 28)}


def test_son_27_columnas_exactas_en_orden():
    assert len(COLUMNAS) == 27
    assert COLUMNAS[0] == "TÍTULO" and COLUMNAS[3] == "TITULAR DEL MEDIO"
    assert COLUMNAS[8] == "EVIDENCIA DE LA NOTICIA (ENLACES)" and COLUMNAS[26] == "OBSERVACIONES"


def test_bloque_corporativo_encabezados_en_fila_4_y_datos_desde_la_5(db):
    crear_nota(db, "Cámara de Comercio de Ibagué lanza ruta", "elolfato.com")
    resumen, wb = _exportar(db)
    ws = wb.active
    assert [ws.cell(4, c).value for c in range(1, 28)] == COLUMNAS
    assert ws["D1"].value == "MONITOREO MEDIOS DE COMUNICACIÓN"
    assert (ws["AA1"].value, ws["AA3"].value) == ("Código: CM-F-005", "Página 1 de 1")
    assert ws["A1"].value is None and ws["A2"].value is None  # sin textos sueltos fuera del bloque
    f = _fila(ws, 5)
    assert (f["TIPO"], f["TITULAR DEL MEDIO"], f["MEDIO"], f["PÁGINA WEB"]) == (
        "Mención", "Cámara de Comercio de Ibagué lanza ruta", "Elolfato", "X",
    )
    assert f["TIPO DE CONTENIDO"] == "PÁGINA WEB" and f["TOTAL PUBLICACIONES"] is None
    assert f["EVIDENCIA DE LA NOTICIA (ENLACES)"].startswith("https://elolfato.com/")
    assert f["FECHA DE PUBLICACIÓN"].date().isoformat() == "2026-10-15"
    assert f["TÍTULO"] is None and f["COSTO"] is None and f["FACEBOOK"] is None
    assert (resumen.filas, resumen.menciones, resumen.replicas) == (1, 1, 0)


def test_solo_validas_del_mes_y_cuenta_las_por_revisar(db):
    crear_nota(db, "Nota de octubre", "a.com")
    crear_nota(db, "Nota de septiembre", "b.com", datetime(2026, 9, 20, 15, tzinfo=UTC))
    crear_nota(db, "Descartada", "c.com", estado=E.DESCARTADA)
    crear_nota(db, "Ambigua", "d.com", estado=E.REVISAR)
    resumen, wb = _exportar(db)
    assert wb.active.max_row == 5  # bloque + encabezado + 1 fila
    assert (resumen.filas, resumen.por_revisar) == (1, 1)


def test_el_mes_se_define_en_hora_de_colombia(db):
    # 01-nov 03:00 UTC = 31-oct 22:00 en Bogotá -> pertenece a octubre
    n = crear_nota(db, "Nota nocturna", "a.com", datetime(2026, 11, 1, 3, 0, tzinfo=UTC))
    assert fecha_local(n).isoformat() == "2026-10-31"
    assert _exportar(db)[0].filas == 1


def test_replicas_agrupadas_y_conteo_una_sola_vez(db):
    crear_nota(db, "Ibagué será sede del Concurso Nacional Cacao de Oro 2026", "caracol.com.co",
               datetime(2026, 10, 10, 15, tzinfo=UTC), via="evento", terminos="Concurso Nacional Cacao de Oro")
    crear_nota(db, "Ibagué será sede del Concurso Nacional Cacao de Oro", "tolimaonline.com",
               datetime(2026, 10, 11, 15, tzinfo=UTC))
    crear_nota(db, "Una nota única sobre formalización empresarial", "ecos.com")
    resumen, wb = _exportar(db)
    ws = wb.active
    filas = [_fila(ws, n) for n in (5, 6, 7)]
    assert [f["TIPO"] for f in filas] == ["Réplica", "Réplica", "Mención"]  # réplicas primero
    assert [f["No MEDIOS QUE REPLICAN EL BOLETIN"] for f in filas] == [2, None, None]
    assert "Réplica provisional" in filas[0]["OBSERVACIONES"]
    assert "evento" in filas[0]["OBSERVACIONES"]
    assert (resumen.menciones, resumen.replicas) == (1, 2)


def test_sentimiento_lleva_el_nombre_del_medio_y_url_sin_resolver_queda_observada(db):
    crear_nota(db, "La CCI inaugura nueva sede y logra récord", "a.com")
    crear_nota(db, "Denuncian irregularidades en proceso", "b.com", url="https://news.google.com/rss/articles/XYZ")
    resumen, wb = _exportar(db)
    ws = wb.active
    por_titular = {_fila(ws, n)["TITULAR DEL MEDIO"]: _fila(ws, n) for n in (5, 6)}
    pos = por_titular["La CCI inaugura nueva sede y logra récord"]
    neg = por_titular["Denuncian irregularidades en proceso"]
    assert (pos["MENCIÓN POSITIVA"], pos["MENCIÓN NEGATIVA"]) == ("A", None)  # nombre del medio en mayúsculas
    assert (neg["MENCIÓN POSITIVA"], neg["MENCIÓN NEGATIVA"]) == (None, "B")
    assert "URL de Google News sin resolver" in neg["OBSERVACIONES"]
    assert resumen.sin_url_real == 1


def test_mes_sin_datos_genera_libro_solo_con_encabezados(db):
    resumen, wb = _exportar(db)
    assert resumen.filas == 0
    assert [wb.active.cell(4, c).value for c in range(1, 28)] == COLUMNAS


# --------------------------------------------------------------- modo plantilla
def _plantilla(tmp_path, encabezados=None):
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "MONITOREO DE MEDIOS - FORMATO CCI"
    for i, nombre in enumerate(encabezados or COLUMNAS, start=1):
        ws.cell(4, i, nombre)
    ws.cell(5, 4).font = Font(bold=True, color="FF0000")  # formato de la primera fila de datos
    ruta = tmp_path / "plantilla.xlsx"
    wb.save(ruta)
    return ruta


def test_modo_plantilla_conserva_filas_previas_y_formato(db, tmp_path):
    crear_nota(db, "Nota A", "a.com")
    crear_nota(db, "Nota B", "b.com")
    ruta = _plantilla(tmp_path)
    _, wb = _exportar(db, plantilla=ruta)
    ws = wb.active
    assert ws["A1"].value == "MONITOREO DE MEDIOS - FORMATO CCI"  # fila 1 intacta
    assert ws.cell(5, 4).value == "Nota A" and ws.cell(6, 4).value == "Nota B"
    assert ws.cell(6, 4).font.bold and ws.cell(6, 4).font.color.rgb.endswith("FF0000")  # hereda el estilo


def test_modo_plantilla_tolera_espacios_y_mayusculas_en_encabezados(db, tmp_path):
    enc = list(COLUMNAS)
    enc[2] = "No MEDIOS QUE REPLICAN EL BOLETIN "  # espacio final, como en los archivos reales
    enc[1] = "tipo"
    enc[5] = "PRECIO"  # febrero lo llama así
    crear_nota(db, "Nota A", "a.com")
    assert _exportar(db, plantilla=_plantilla(tmp_path, enc))[0].filas == 1


def test_plantilla_con_encabezados_distintos_falla_con_mensaje_claro(db, tmp_path):
    enc = list(COLUMNAS)
    enc[4] = "NOMBRE DEL MEDIO"
    with pytest.raises(PlantillaInvalida, match="col 5"):
        _exportar(db, plantilla=_plantilla(tmp_path, enc))


# ------------------------------------------------------- clasificación provisional
def test_mismo_medio_repetido_no_es_replica(db):
    a = crear_nota(db, "Titular idéntico de prueba", "a.com")
    b = crear_nota(db, "Titular idéntico de prueba", "a.com")
    assert {i.tipo for i in clasificar([a, b]).values()} == {TipoRegistro.MENCION}


def test_lexico_de_sentimiento():
    assert sentimiento_lexico("Lanzan alianza que impulsa el crecimiento") == Sentimiento.POSITIVO
    assert sentimiento_lexico("Crisis y denuncia por fraude") == Sentimiento.NEGATIVO
    assert sentimiento_lexico("Reunión de empresarios en Ibagué") == Sentimiento.NEUTRO
