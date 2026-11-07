import { useId, useState, type ReactNode } from 'react'

interface Props {
  titulo: string
  subtitulo?: string
  grafica: ReactNode
  tabla: ReactNode
  /** Controles de leyenda (HTML) que van sobre la gráfica */
  leyenda?: ReactNode
}

/** Tarjeta con gráfica y su gemela en tabla (la tabla es la vía accesible a cada valor). */
export function ChartCard({ titulo, subtitulo, grafica, tabla, leyenda }: Props) {
  const [vista, setVista] = useState<'grafica' | 'tabla'>('grafica')
  const id = useId()
  return (
    <section className="rounded-xl border border-edge bg-surface p-5" aria-labelledby={id}>
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h2 id={id} className="text-base font-semibold">
            {titulo}
          </h2>
          {subtitulo && <p className="mt-0.5 text-sm text-ink2">{subtitulo}</p>}
        </div>
        <div className="flex shrink-0 rounded-lg border border-edge p-0.5 text-sm" role="group" aria-label="Vista">
          {(['grafica', 'tabla'] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={vista === v}
              onClick={() => setVista(v)}
              className={`rounded-md px-2.5 py-1 ${vista === v ? 'bg-wash font-medium text-ink' : 'text-ink2 hover:bg-wash'}`}
            >
              {v === 'grafica' ? 'Gráfica' : 'Tabla'}
            </button>
          ))}
        </div>
      </div>
      {vista === 'grafica' ? (
        <>
          {leyenda}
          {grafica}
        </>
      ) : (
        tabla
      )}
    </section>
  )
}
