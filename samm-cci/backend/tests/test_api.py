from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.orm import sessionmaker

from app.api.routes import get_config, get_exports_dir
from app.database import get_session
from app.main import app
from app.services.exporter import COLUMNAS
from tests.conftest import crear_nota


@pytest.fixture
def client(engine, db, tmp_path):
    Sesion = sessionmaker(bind=engine, expire_on_commit=False)

    def _sesion():
        with Sesion() as s:
            yield s

    app.dependency_overrides[get_session] = _sesion
    app.dependency_overrides[get_config] = lambda: {}
    app.dependency_overrides[get_exports_dir] = lambda: tmp_path / "exports"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_meses_metricas_y_menciones(client, db):
    from app.models import EstadoRelevancia as E

    crear_nota(db, "Ibagué será sede del Concurso Nacional Cacao de Oro", "caracol.com.co")
    crear_nota(db, "Ibagué será sede del Concurso Nacional Cacao de Oro 2026", "tolimaonline.com")
    crear_nota(db, "Cámara de Comercio inaugura nueva sede", "ecos.com")
    crear_nota(db, "Nota de agosto", "x.com", datetime(2026, 8, 5, 15, tzinfo=UTC))
    crear_nota(db, "Ambigua", "y.com", estado=E.REVISAR)

    assert client.get("/api/meses").json() == ["2026-10", "2026-08"]

    r = client.get("/api/metricas/mensual", params={"ultimos": 4}).json()
    assert r["provisional"] is True
    assert [m["mes"] for m in r["meses"]] == ["2026-07", "2026-08", "2026-09", "2026-10"]  # continuo
    por_mes = {m["mes"]: m for m in r["meses"]}
    assert por_mes["2026-09"]["total"] == 0
    oct_ = por_mes["2026-10"]
    claves = ("total", "replicas", "menciones", "positivas", "por_revisar")
    assert tuple(oct_[k] for k in claves) == (3, 2, 1, 1, 1)

    resumen = client.get("/api/resumen", params={"mes": "2026-10"}).json()
    assert resumen["total"] == 3 and resumen["por_revisar"] == 1

    notas = client.get("/api/menciones", params={"mes": "2026-10"}).json()
    assert len(notas) == 3 and {n["tipo"] for n in notas} == {"Mención", "Réplica"}

    semanal = client.get("/api/metricas/semanal", params={"mes": "2026-10"}).json()
    assert sum(s["total"] for s in semanal["semanas"]) == 3


def test_exportar_descarga_xlsx(client, db):
    crear_nota(db, "Cámara de Comercio de Ibagué lanza ruta", "elolfato.com")
    r = client.get("/api/export/xlsx", params={"mes": "2026-10"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="Monitoreo_de_Medios_2026-10.xlsx"' in r.headers["content-disposition"]
    assert r.headers["x-filas"] == "1"
    ws = load_workbook(BytesIO(r.content)).active
    assert [ws.cell(4, c).value for c in range(1, 28)] == COLUMNAS


@pytest.mark.parametrize("ruta", ["/api/export/xlsx", "/api/resumen", "/api/menciones", "/api/metricas/semanal"])
@pytest.mark.parametrize("mes", ["2026-13", "octubre", "2026-1"])
def test_mes_invalido_da_422(client, ruta, mes):
    assert client.get(ruta, params={"mes": mes}).status_code == 422


def test_sin_datos_devuelve_listas_vacias(client):
    assert client.get("/api/meses").json() == []
    assert client.get("/api/metricas/mensual").json() == {"provisional": True, "meses": []}


def test_exportacion_se_guarda_y_se_puede_redescargar(client, db):
    assert client.get("/api/exportaciones").json() == []
    crear_nota(db, "Cámara de Comercio de Ibagué lanza ruta", "elolfato.com")
    r = client.get("/api/export/xlsx", params={"mes": "2026-10"})
    guardado = r.headers["x-archivo-guardado"]

    lista = client.get("/api/exportaciones").json()
    assert len(lista) == 1
    assert lista[0]["nombre"] == guardado and lista[0]["mes"] == "2026-10" and lista[0]["filas"] == 1
    assert lista[0]["bytes"] > 0

    d = client.get(f"/api/exportaciones/{guardado}")
    assert d.status_code == 200 and d.content == r.content


@pytest.mark.parametrize("nombre", ["..%2F..%2F.env", "samm.db", "Monitoreo_de_Medios_2026-10.xlsx", "x.xlsx"])
def test_descarga_exportacion_rechaza_nombres_raros(client, nombre):
    assert client.get(f"/api/exportaciones/{nombre}").status_code == 404
