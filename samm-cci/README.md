# SAMM-CCI · Sistema Automatizado de Monitoreo de Medios

Monitoreo automático de menciones y réplicas de la Cámara de Comercio de Ibagué en medios digitales.

## Estado

- [x] Fase 1: arquitectura y estructura
- [x] Fase 2: modelo de datos + extractor Google News RSS + pipeline con deduplicación
- [x] Fase 3: extracción del cuerpo + validación de relevancia (entidad, eventos clave, descartes auditables)
- [x] Fase 4: exportador Excel (27 columnas), API FastAPI y dashboard React (TIPO y sentimiento provisionales)
- [x] Fase 5a: Alembic, importador del histórico ene-oct, exportador alineado al formato real CM-F-005, medición del acierto
- [ ] Fase 5b: clasificador real Mención/Réplica con los boletines (sembrados por el histórico) y sentimiento
- [ ] Fase 6: scheduler diario y pulido para portafolio

## Arranque rápido (Windows 11, PowerShell)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m pytest -q            # pruebas (no usan internet)
python -m app.cli init-db      # crea backend/data/samm.db
python -m app.cli extract      # busca notas nuevas y valida su relevancia (usa internet)
python -m app.cli validate     # valida las pendientes (descarga el cuerpo de cada nota)
python -m app.cli revalidar    # reaplica las reglas sin internet, tras editar sources.yaml
python -m app.cli listar --estado Revisar     # Válida | Descartada | Revisar | Pendiente

python ../scripts/evaluate_relevance.py       # acierto contra tests/gold_set/relevancia.csv
```

## Base de datos y migraciones (Alembic)

`python -m app.cli init-db` (y al arrancar la API) aplica las migraciones de `backend/migraciones/`. Una base creada
en las fases anteriores se reconoce sola: conserva sus datos y recibe solo lo nuevo. Nunca más hay que borrar `samm.db`.
Cuando cambies un modelo: `alembic -c alembic.ini revision --autogenerate -m "descripcion"` (desde `backend/`) y revisa
el archivo generado; la prueba `test_migraciones.py` falla si el modelo y las migraciones se desalinean.

## Histórico: importar los Excel mensuales

```powershell
cd backend
python -m app.cli importar "C:\ruta\historico" --dry-run --reporte anomalias.csv   # simulacro: no guarda nada
python -m app.cli importar "C:\ruta\historico"                                   # importa (se puede repetir sin duplicar)
python -m app.cli evaluar                                                          # acierto del clasificador vs. tus etiquetas
```

El importador mapea las columnas por nombre (no por posición), ignora hojas que no son de datos, repara años mal
escritos hacia el mes del archivo, trata `NA` como vacío, acepta cualquier texto en redes y sentimiento, propaga el
TÍTULO de las celdas combinadas y, si una URL aparece en varias hojas/archivos, conserva la versión con más campos
llenos. Cada anomalía queda en el CSV con archivo, hoja y fila.

## Dashboard y Excel

```powershell
# Terminal 1: API  ->  http://127.0.0.1:8000  (documentación interactiva en /docs)
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal 2: dashboard  ->  http://localhost:5173
cd frontend
npm install
npm run dev

# Excel del mes desde la terminal (sin dashboard)
python -m app.cli exportar --mes 2026-10
python -m app.cli exportar --mes 2026-10 --plantilla "C:\ruta\Monitoreo de Medios octubre.xlsx"
```

Con `--plantilla` (o `PLANTILLA_XLSX` en `.env`) el Excel se genera sobre tu archivo real (usa uno SIN filas de datos:
las agrega después de las existentes), conservando formato, anchos y las filas 1-3. Sin plantilla se crea uno desde cero
con el bloque corporativo CM-F-005 en las filas 1-3 y los 27 encabezados en la fila 4. Sentimiento = nombre del medio en
mayúsculas; redes = "X"; TOTAL PUBLICACIONES queda vacío.
El dashboard compara los últimos 6/12/24 meses, muestra el sentimiento y el detalle semanal, y tiene
una vista de tabla para cada gráfica.

Si PowerShell bloquea la activación del entorno: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Excel desde la web

El botón **Exportar a Excel** descarga el archivo y además guarda una copia en `backend/data/exports/`
(carpeta ignorada por Git). El panel **Mis Excel generados** del dashboard lista esas copias para
volver a descargarlas. API: `GET /api/exportaciones` y `GET /api/exportaciones/{nombre}`.
La carpeta se puede cambiar con `EXPORTS_DIR` en `.env`.

## Configuración

Consultas, eventos clave (con alias), reglas de relevancia y dominios excluidos viven en
`backend/config/sources.yaml`. Para agregar un evento anual basta una entrada en `eventos:`.

## Validación de relevancia

Una nota es **Válida** si su titular, resumen o cuerpo menciona a la CCI (nombre completo, @CamaraIbague;
"Cámara de Comercio"/"CCI" solo con contexto de Ibagué/Tolima) o un evento clave. **Descartada** si se leyó
el cuerpo y no hay nada. **Revisar** si es ambigua o no se pudo leer el cuerpo: nunca se descarta a ciegas.

## Modelo de datos

- `menciones`: titular y URL (obligatorios), medio, dominio, fecha de publicación, día de monitoreo,
  tipo (Mención / Réplica / Sin clasificar), sentimiento, boletín asociado.
- `boletines`: comunicados enviados a prensa (base para detectar réplicas).
- `ejecuciones`: bitácora de cada corrida (encontrados, nuevos, duplicados, errores).
