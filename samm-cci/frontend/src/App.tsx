import { useState } from 'react'
import { descargarExcel, type Exportacion, type Mensual, type Nota, type Resumen, type Semanal } from './api'
import { ChartCard } from './components/ChartCard'
import { ExcelsGenerados } from './components/ExcelsGenerados'
import { GroupedBars, Leyenda, TablaGemela, type Serie } from './components/GroupedBars'
import { KpiTile } from './components/KpiTile'
import { NotasTabla } from './components/NotasTabla'
import { useApi } from './hooks/useApi'
import { etiquetaMes, etiquetaSemana, nombreMes, numero } from './lib/format'

const SERIES_TIPO: Serie[] = [
  { clave: 'menciones', nombre: 'Menciones', color: 'var(--series-1)' },
  { clave: 'replicas', nombre: 'Réplicas', color: 'var(--series-2)' },
]
const SERIES_SENTIMIENTO: Serie[] = [
  { clave: 'positivas', nombre: 'Positivo', color: 'var(--good)', glifo: '▲' },
  { clave: 'negativas', nombre: 'Negativo', color: 'var(--critical)', glifo: '▼' },
]
const RANGOS = [6, 12, 24] as const

export default function App() {
  const meses = useApi<string[]>('/api/meses')
  const [elegido, setElegido] = useState<string | null>(null)
  const [ultimos, setUltimos] = useState<number>(6)
  const [aviso, setAviso] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null)
  const [exportando, setExportando] = useState(false)
  const [versionExcels, setVersionExcels] = useState(0)

  const mes = elegido ?? meses.data?.[0] ?? null
  const mensual = useApi<Mensual>(`/api/metricas/mensual?ultimos=${ultimos}`)
  const resumen = useApi<Resumen>(mes ? `/api/resumen?mes=${mes}` : null)
  const semanal = useApi<Semanal>(mes ? `/api/metricas/semanal?mes=${mes}` : null)
  const notas = useApi<Nota[]>(mes ? `/api/menciones?mes=${mes}` : null)
  const excels = useApi<Exportacion[]>('/api/exportaciones', versionExcels)

  const cargando = [meses, mensual, resumen, semanal, notas].some((q) => q.cargando)
  const error = [meses, mensual, resumen, semanal, notas].find((q) => q.error)?.error
  const provisional = Boolean(mensual.data?.provisional || resumen.data?.provisional)

  // Variación contra el mes anterior (solo si ese mes está en la serie)
  const serie = mensual.data?.meses ?? []
  const idx = serie.findIndex((m) => m.mes === mes)
  const previo = idx > 0 ? serie[idx - 1] : undefined
  const delta = (k: 'total' | 'menciones' | 'replicas') =>
    resumen.data && previo ? { valor: resumen.data[k] - previo[k], contra: nombreMes(previo.mes) } : undefined

  async function exportar() {
    if (!mes) return
    setExportando(true)
    setAviso(null)
    try {
      const r = await descargarExcel(mes)
      const extra = r.porRevisar ? ` ${r.porRevisar} notas del mes están en «Revisar» y no se incluyeron.` : ''
      setAviso({ tipo: 'ok', texto: `${r.archivo} descargado: ${r.filas} filas. Quedó guardado en «Mis Excel generados».${extra}` })
      setVersionExcels((v) => v + 1)
    } catch (e) {
      setAviso({ tipo: 'error', texto: e instanceof Error ? e.message : 'No se pudo exportar' })
    } finally {
      setExportando(false)
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">SAMM-CCI · Monitoreo de medios</h1>
          <p className="text-sm text-ink2">Cámara de Comercio de Ibagué · notas válidas, menciones y réplicas</p>
        </div>
        <button
          type="button"
          onClick={exportar}
          disabled={!mes || exportando}
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-40"
        >
          {exportando ? 'Generando…' : 'Exportar a Excel'}
        </button>
      </header>

      {/* Una sola fila de filtros sobre todo lo que filtra */}
      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-ink2">Mes</span>
          <select
            value={mes ?? ''}
            onChange={(e) => setElegido(e.target.value)}
            disabled={!meses.data?.length}
            className="rounded-lg border border-edge bg-surface px-2.5 py-1.5"
          >
            {(meses.data ?? []).map((m) => (
              <option key={m} value={m}>
                {nombreMes(m)}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-2">
          <span className="text-ink2">Comparar</span>
          <div className="flex rounded-lg border border-edge p-0.5" role="group" aria-label="Meses a comparar">
            {RANGOS.map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={ultimos === r}
                onClick={() => setUltimos(r)}
                className={`rounded-md px-2.5 py-1 ${ultimos === r ? 'bg-wash font-medium' : 'text-ink2 hover:bg-wash'}`}
              >
                Últimos {r} meses
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="mt-5 rounded-xl border border-edge bg-surface p-4 text-sm">
          <strong>No se pudo cargar la información.</strong> {error}. ¿Está corriendo el backend?{' '}
          <code className="rounded bg-wash px-1.5 py-0.5">uvicorn app.main:app --reload</code> (carpeta backend)
        </div>
      )}
      {aviso && (
        <div role="status" className="mt-5 rounded-xl border border-edge bg-surface p-3 text-sm">
          {aviso.texto}
        </div>
      )}
      {provisional && (
        <div
          className="mt-5 rounded-xl px-4 py-3 text-sm"
          style={{ background: 'var(--notice-bg)', color: 'var(--notice-ink)' }}
        >
          <strong>Clasificación provisional.</strong> «Mención/Réplica» se estima por titulares repetidos en varios medios y el
          sentimiento por un léxico básico. Serán reemplazados al conectar los boletines y el modelo de sentimiento.
        </div>
      )}

      {!error && meses.data && meses.data.length === 0 && (
        <p className="mt-8 text-sm text-ink2">
          Aún no hay notas válidas. Ejecuta <code className="rounded bg-wash px-1.5 py-0.5">python -m app.cli extract</code> en la
          carpeta backend.
        </p>
      )}

      {mes && (
        <main className={`mt-5 space-y-5 transition-opacity ${cargando ? 'opacity-60' : ''}`} aria-busy={cargando}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTile etiqueta={`Notas válidas · ${nombreMes(mes)}`} valor={numero(resumen.data?.total ?? 0)} delta={delta('total')} />
            <KpiTile etiqueta="Menciones" valor={numero(resumen.data?.menciones ?? 0)} delta={delta('menciones')} />
            <KpiTile etiqueta="Réplicas" valor={numero(resumen.data?.replicas ?? 0)} delta={delta('replicas')} />
            <KpiTile etiqueta="Por revisar" valor={numero(resumen.data?.por_revisar ?? 0)} nota="Ambiguas o sin cuerpo; no se exportan" />
          </div>

          <ChartCard
            titulo="Menciones vs. réplicas por mes"
            subtitulo="Haz clic en un mes para ver su detalle"
            leyenda={<Leyenda series={SERIES_TIPO} />}
            grafica={
              <GroupedBars
                datos={serie as unknown as Record<string, string | number>[]}
                xClave="mes"
                xFormato={etiquetaMes}
                series={SERIES_TIPO}
                seleccionado={mes}
                onSelect={setElegido}
              />
            }
            tabla={
              <TablaGemela
                datos={serie as unknown as Record<string, string | number>[]}
                xClave="mes"
                xTitulo="Mes"
                xFormato={etiquetaMes}
                columnas={[
                  { clave: 'menciones', titulo: 'Menciones' },
                  { clave: 'replicas', titulo: 'Réplicas' },
                  { clave: 'total', titulo: 'Total' },
                ]}
              />
            }
          />

          <div className="grid gap-5 lg:grid-cols-2">
            <ChartCard
              titulo="Sentimiento por mes"
              subtitulo="Notas positivas y negativas"
              leyenda={<Leyenda series={SERIES_SENTIMIENTO} />}
              grafica={
                <GroupedBars
                  datos={serie as unknown as Record<string, string | number>[]}
                  xClave="mes"
                  xFormato={etiquetaMes}
                  series={SERIES_SENTIMIENTO}
                  seleccionado={mes}
                  onSelect={setElegido}
                />
              }
              tabla={
                <TablaGemela
                  datos={serie as unknown as Record<string, string | number>[]}
                  xClave="mes"
                  xTitulo="Mes"
                  xFormato={etiquetaMes}
                  columnas={[
                    { clave: 'positivas', titulo: 'Positivo' },
                    { clave: 'negativas', titulo: 'Negativo' },
                    { clave: 'neutras', titulo: 'Neutro' },
                  ]}
                />
              }
            />
            <ChartCard
              titulo={`Detalle semanal · ${nombreMes(mes)}`}
              subtitulo="Semanas de lunes a domingo"
              leyenda={<Leyenda series={SERIES_TIPO} />}
              grafica={
                <GroupedBars
                  datos={(semanal.data?.semanas ?? []) as unknown as Record<string, string | number>[]}
                  xClave="semana_inicio"
                  xFormato={etiquetaSemana}
                  series={SERIES_TIPO}
                />
              }
              tabla={
                <TablaGemela
                  datos={(semanal.data?.semanas ?? []) as unknown as Record<string, string | number>[]}
                  xClave="semana_inicio"
                  xTitulo="Semana"
                  xFormato={etiquetaSemana}
                  columnas={[
                    { clave: 'menciones', titulo: 'Menciones' },
                    { clave: 'replicas', titulo: 'Réplicas' },
                    { clave: 'total', titulo: 'Total' },
                  ]}
                />
              }
            />
          </div>

          <section className="rounded-xl border border-edge bg-surface p-5" aria-labelledby="t-notas">
            <h2 id="t-notas" className="mb-3 text-base font-semibold">
              Notas de {nombreMes(mes)}
            </h2>
            <NotasTabla notas={notas.data ?? []} />
          </section>

          <section className="rounded-xl border border-edge bg-surface p-5" aria-labelledby="t-excels">
            <h2 id="t-excels" className="mb-3 text-base font-semibold">
              Mis Excel generados
            </h2>
            <ExcelsGenerados items={excels.data ?? []} />
          </section>
        </main>
      )}
    </div>
  )
}
