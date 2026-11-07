from datetime import date, datetime

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.importers import normalizar as nz
from app.importers.cargar import importar
from app.models import Boletin, FuenteOrigen, Mencion, Sentimiento, TipoRegistro
from app.services.evaluacion import evaluar
from app.services.exporter import COLUMNAS, exportar_xlsx

REF = (2026, 10)
BOLETIN = "NegociaTECH superó expectativas y generó negocios"


# ------------------------------------------------------------------ normalización
@pytest.mark.parametrize("valor", [None, "", "  ", "NA", "n/a", "-"])
def test_na_es_vacio(valor):
    assert nz.es_na(valor) and nz.limpiar_texto(valor) is None


def test_limpiar_texto_colapsa_espacios_y_letras_matematicas():
    assert nz.limpiar_texto(" La Cámara\nde   Comercio ") == "La Cámara de Comercio"
    assert nz.limpiar_texto("𝗖𝗮́𝗺𝗮𝗿𝗮 𝗱𝗲 𝗖𝗼𝗺𝗲𝗿𝗰𝗶𝗼") == "Cámara de Comercio"


@pytest.mark.parametrize(
    ("valor", "esperada", "nota"),
    [
        (datetime(2026, 10, 3), date(2026, 10, 3), None),
        ("14/10/2026", date(2026, 10, 14), None),
        ("14/10/0206", date(2026, 10, 14), "año corregido"),  # año mal digitado
        (datetime(3036, 10, 2), date(2026, 10, 2), "año corregido"),
        (datetime(2025, 10, 9), date(2026, 10, 9), "año corregido"),  # cae en el mes del archivo
        (datetime(2025, 9, 20), date(2025, 9, 20), None),  # mes anterior legítimo: NO se toca
        ("NA", None, "sin fecha"),
        ("mañana", None, "fecha ilegible"),
    ],
)
def test_parse_fecha(valor, esperada, nota):
    d, n = nz.parse_fecha(valor, REF)
    assert d == esperada
    assert (n is None) if nota is None else (n or "").startswith(nota)


def test_diciembre_en_un_archivo_de_enero_no_se_repara():
    assert nz.parse_fecha(datetime(2025, 12, 20), (2026, 1))[0] == date(2025, 12, 20)


def test_sentimiento_acepta_el_nombre_del_medio_y_ignora_na():
    assert nz.parse_sentimiento("TOLIMA ONLINE", None)[0] == Sentimiento.POSITIVO
    assert nz.parse_sentimiento("NA", "x")[0] == Sentimiento.NEGATIVO
    assert nz.parse_sentimiento("NA", "NA") == (None, None)  # sin etiquetar, no "neutro"
    assert nz.parse_sentimiento("x", "x")[0] is None


def test_redes_cualquier_texto_cuenta():
    valores = {"FACEBOOK": "x", "INSTAGRAM": "NA", "X": "TOLIMA STEREO", "LINKEDIN": None}
    assert nz.redes_marcadas(valores) == "FACEBOOK,X"


# ------------------------------------------------------------------ libros de prueba
def _libro(ruta, hojas, *, sin_costo=False):
    """hojas: {nombre: [fila(dict nombre_columna -> valor)]} con el bloque corporativo en las filas 1-3."""
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        ws["D1"] = "MONITOREO MEDIOS DE COMUNICACIÓN"
        ws["AA1"] = "Código: CM-F-005"
        ws["AA3"] = "Página 1 de 1"
        columnas = [c for c in COLUMNAS if not (sin_costo and c == "COSTO")]
        for i, c in enumerate(columnas, start=1):
            ws.cell(4, i, c + (" " if c == "TIPO DE CONTENIDO" else ""))  # espacios sobrantes como en el real
        for r, fila in enumerate(filas, start=5):
            for i, c in enumerate(columnas, start=1):
                if c in fila:
                    ws.cell(r, i, fila[c])
    wb.create_sheet("GRAFICA")["A1"] = "no es una hoja de datos"
    wb.save(ruta)
    return ruta


def _f(tipo, titular, medio, dia, url, **extra):
    return {"TIPO": tipo, "TITULAR DEL MEDIO": titular, "MEDIO": medio,
            "FECHA DE PUBLICACIÓN": datetime(2026, 10, dia), "EVIDENCIA DE LA NOTICIA (ENLACES)": url, **extra}


@pytest.fixture
def octubre(tmp_path):
    return _libro(
        tmp_path / "MONITOREO_OCTUBRE_2026.xlsx",
        {
            "Hoja 1": [
                _f("Réplica", "NegociaTECH superó expectativas", "TOLIMA STEREO", 3, "https://tolimastereo.com/a",
                   **{"TÍTULO": BOLETIN, "FACEBOOK": "x", "TIPO DE CONTENIDO": "FACEBOOK"}),
                _f("Réplica", "NegociaTECH superó expectativas", "TOLIMA ONLINE", 3,
                   "https://tolimaonline.com/a?utm_source=x", **{"TÍTULO": BOLETIN}),
                _f("Mención", "Ibagué crece", "ECOS", 5, "https://ecos.com/b",
                   **{"MENCIÓN POSITIVA": "ECOS", "MENCIÓN NEGATIVA": "NA"}),
                _f("Mención", "Sin enlace", "RADIO X", 6, "NA"),
            ]
        },
    )


def test_importa_etiquetas_boletin_y_archivos_ignorados(db, octubre):
    rep = importar(db, [octubre])
    assert (rep.filas_leidas, rep.importadas, rep.boletines_creados) == (4, 4, 1)  # GRAFICA se ignora
    filas = {m.titular: m for m in db.scalars(select(Mencion))}
    a = db.scalars(select(Mencion).where(Mencion.dominio == "tolimastereo.com")).one()
    assert a.origen == FuenteOrigen.HISTORICO and a.tipo == TipoRegistro.REPLICA and a.boletin_id
    assert a.redes == "FACEBOOK" and a.tipo_contenido == "FACEBOOK"
    assert db.scalars(select(Boletin)).one().titular.startswith("NegociaTECH superó")
    assert filas["Ibagué crece"].sentimiento == Sentimiento.POSITIVO and filas["Ibagué crece"].boletin_id is None
    assert filas["Sin enlace"].url_canonica.startswith("sin-enlace://")
    assert [a.codigo for a in rep.anomalias] == ["sin_enlace"]


def test_dry_run_no_guarda_y_reimportar_no_duplica(db, octubre):
    rep = importar(db, [octubre], dry_run=True)
    assert rep.importadas == 4 and db.scalars(select(Mencion)).all() == []
    importar(db, [octubre])
    segunda = importar(db, [octubre])
    assert (segunda.importadas, segunda.ya_existentes) == (0, 4)
    assert len(db.scalars(select(Mencion)).all()) == 4


def test_duplicados_entre_hojas_conserva_la_version_mas_completa(db, tmp_path):
    vacia = _f("Mención", "Nota repetida", "ECOS", 5, "https://ecos.com/z")
    extra = {"TIPO DE CONTENIDO": "PÁGINA WEB", "OBSERVACIONES": "ok"}
    llena = _f("Mención", "Nota repetida", "ECOS", 5, "https://www.ecos.com/z/", **extra)
    ruta = _libro(tmp_path / "Monitoreo_octubre_2026.xlsx", {"Hoja 1": [vacia], "Copia": [llena]})
    rep = importar(db, [ruta])
    assert (rep.importadas, rep.duplicados_descartados) == (1, 1)
    assert db.scalars(select(Mencion)).one().observaciones == "ok"


def test_plantilla_de_26_columnas_se_lee_por_nombre(db, tmp_path):
    ruta = _libro(tmp_path / "Monitoreo_enero_2026.xlsx", {"Enero": [
        {"TIPO": "Mención", "TÍTULO": "Titular en TÍTULO", "MEDIO": "ECOS",
         "FECHA DE PUBLICACIÓN": datetime(2026, 1, 9), "EVIDENCIA DE LA NOTICIA (ENLACES)": "https://ecos.com/ene"}]},
        sin_costo=True)
    importar(db, [ruta])
    m = db.scalars(select(Mencion)).one()
    assert (m.titular, m.fecha_publicacion.date()) == ("Titular en TÍTULO", date(2026, 1, 9))


def test_titulo_en_celdas_combinadas_se_propaga(db, tmp_path):
    ruta = _libro(tmp_path / "MONITOREO_OCTUBRE_2026.xlsx", {"Hoja 1": [
        _f("Réplica", "Variante uno", "A", 3, "https://a.com/1", **{"TÍTULO": "Boletín compartido"}),
        _f("Réplica", "Variante dos", "B", 4, "https://b.com/2"),
        _f("Réplica", "Variante tres", "C", 4, "https://c.com/3")]})
    from openpyxl import load_workbook

    wb = load_workbook(ruta)
    wb["Hoja 1"].merge_cells("A5:A7")
    wb.save(ruta)
    rep = importar(db, [ruta])
    assert rep.boletines_creados == 1
    assert {m.boletin.titular for m in db.scalars(select(Mencion))} == {"Boletín compartido"}


# ------------------------------------------------------------------ integración con exportador y evaluación
def test_lo_importado_se_exporta_con_las_convenciones_de_la_plantilla(db, octubre, tmp_path):
    importar(db, [octubre])
    destino = tmp_path / "salida.xlsx"
    r = exportar_xlsx(db, {}, 2026, 10, destino)
    from openpyxl import load_workbook

    ws = load_workbook(destino).active
    fila = {ws.cell(4, c).value: [ws.cell(r_, c).value for r_ in range(5, 9)] for c in range(1, 28)}
    assert r.filas == 4 and fila["TIPO"][:2] == ["Réplica", "Réplica"]
    assert fila["No MEDIOS QUE REPLICAN EL BOLETIN"][:2] == [2, None]
    assert fila["TÍTULO"][0].startswith("NegociaTECH") and fila["FACEBOOK"][0] == "X"
    assert "ECOS" in fila["MENCIÓN POSITIVA"]  # sentimiento = nombre del medio
    assert all(v is None for v in fila["TOTAL PUBLICACIONES"])


def test_evaluar_compara_contra_las_etiquetas(db, octubre):
    importar(db, [octubre])
    ev = evaluar(db, {})
    assert ev.tipo.total == 4 and ev.tipo.acierto == 1.0  # las dos réplicas comparten titular
    assert (ev.sentimiento.total, ev.sin_etiqueta_sentimiento) == (1, 3)
