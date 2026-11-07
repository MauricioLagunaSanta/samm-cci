"""Casos basados en el feedback de la comunicadora de la CCI (nov-2026)."""
import pytest

from app.classification.relevance import compilar_reglas, evaluar, normalize
from app.config import load_sources
from app.models import EstadoRelevancia as E

CONFIG = load_sources()
REGLAS = compilar_reglas(CONFIG)

RELLENO = (
    "El pasado fin de semana se desarrolló una jornada con empresarios y ciudadanos de la región. "
    "Las autoridades indicaron que continuarán las actividades durante las próximas semanas. "
) * 3


def ev(titular, cuerpo, resumen=None):
    return evaluar(titular, resumen, cuerpo, REGLAS)


def test_normalize_quita_tildes_y_signos():
    assert normalize("¡Cámara de Comercio, de Ibagué!") == "camara de comercio de ibague"


# --- Falsos positivos que la comunicadora pidió descartar -----------------------------------
@pytest.mark.parametrize(
    "titular",
    [
        "Voraz incendio consumió una vivienda",
        "¿Ébola o malaria? La enfermedad que tiene en alerta a MinSalud",
        "Más de $126.000 millones para salud",
    ],
)
def test_falsos_positivos_se_descartan(titular):
    r = ev(titular, RELLENO)
    assert r.estado == E.DESCARTADA and r.via is None


def test_nota_sin_mencion_a_la_camara_se_descarta():
    """Nota 6: 'esa está buena, pero no menciona a la Cámara'."""
    r = ev("Treinta billones de razones para revisar su negocio hoy", RELLENO + " Comercio exterior.")
    assert r.estado == E.DESCARTADA


# --- Menciones directas ---------------------------------------------------------------------
def test_mencion_directa_en_el_cuerpo():
    cuerpo = RELLENO + " Según la Cámara de Comercio de Ibagué, ..."
    r = ev("Ingetécnicas y Hertelec: el legado familiar", cuerpo)
    assert (r.estado, r.via) == (E.VALIDA, "entidad")


def test_mencion_directa_en_titular_sin_cuerpo():
    r = ev("Cámara de Comercio de Ibagué lanza ruta exportadora", None)
    assert (r.estado, r.via) == (E.VALIDA, "entidad")
    assert "sin cuerpo" in r.motivo


def test_arroba_de_la_cuenta():
    assert ev("Nota", RELLENO + " Etiquetó a @CamaraIbague en la publicación.").estado == E.VALIDA


# --- Eventos que apoya la CCI ---------------------------------------------------------------
def test_evento_cacao_de_oro_es_valido_aunque_no_cite_a_la_camara():
    r = ev("Ibagué será sede del Concurso Nacional Cacao de Oro 2026", RELLENO)
    assert (r.estado, r.via) == (E.VALIDA, "evento")


def test_evento_moda_detectado_en_el_cuerpo():
    """Nota 8: titular irrelevante, pero el cuerpo cita la feria que apoya la Cámara."""
    r = ev(
        "¿A quién le sirve la moda de la delgadez extrema?",
        RELLENO + " Durante la feria Ibagué, Negocios y Moda se debatió el tema.",
    )
    assert (r.estado, r.via) == (E.VALIDA, "evento")


def test_alias_de_evento():
    assert ev("Nota", RELLENO + " Ganó el Cacao de Oro.").via == "evento"


# --- Entidad débil: no confundir con otras cámaras ------------------------------------------
def test_otra_camara_de_comercio_no_cuenta():
    r = ev("Informe económico", RELLENO + " La Cámara de Comercio de Bogotá presentó cifras.")
    assert r.estado == E.DESCARTADA


def test_camara_de_comercio_con_contexto_local_es_valida():
    cuerpo = RELLENO + " La Cámara de Comercio, con sede en Ibagué, capacitó a 200 comerciantes."
    r = ev("Formalización", cuerpo)
    assert (r.estado, r.via) == (E.VALIDA, "entidad_debil")


def test_camara_de_comercio_sin_contexto_va_a_revisar():
    r = ev("Cifras", RELLENO + " La Cámara de Comercio informó que las ventas crecieron.")
    assert r.estado == E.REVISAR


def test_sigla_cci_necesita_contexto_local():
    assert ev("Nota", RELLENO + " La CCI informó cifras de Ibagué.").estado == E.VALIDA
    assert ev("Nota", RELLENO + " La CCI informó cifras de Bogotá.").estado == E.REVISAR
    minuscula = RELLENO + " La sigla cci en minúscula no cuenta, ni siquiera en Ibagué."
    assert ev("Nota", minuscula).estado == E.DESCARTADA


def test_sin_cuerpo_y_sin_pistas_va_a_revisar_nunca_se_descarta():
    r = ev("Más de $126.000 millones para salud", None)
    assert r.estado == E.REVISAR
