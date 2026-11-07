import type { Nota } from '../api'
import { etiquetaFecha } from '../lib/format'

const VIA: Record<string, string> = {
  entidad: 'Cita a la CCI',
  entidad_debil: 'Contexto local',
  evento: 'Evento apoyado',
}
const SENT: Record<Nota['sentimiento'], { glifo: string; color: string }> = {
  Positivo: { glifo: '▲', color: 'var(--good)' },
  Negativo: { glifo: '▼', color: 'var(--critical)' },
  Neutro: { glifo: '●', color: 'var(--muted)' },
}

export function NotasTabla({ notas }: { notas: Nota[] }) {
  if (!notas.length) return <p className="py-6 text-sm text-ink2">No hay notas válidas en este mes.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-ink2">
            <th className="py-2 pr-4 font-medium">Titular</th>
            <th className="py-2 pr-4 font-medium">Medio</th>
            <th className="py-2 pr-4 font-medium">Fecha</th>
            <th className="py-2 pr-4 font-medium">Tipo</th>
            <th className="py-2 pr-4 font-medium">Sentimiento</th>
            <th className="py-2 font-medium">Por qué es relevante</th>
          </tr>
        </thead>
        <tbody>
          {notas.map((n) => (
            <tr key={n.id} className="border-b border-line align-top last:border-0">
              <td className="max-w-[34rem] py-2 pr-4">
                <a href={n.url} target="_blank" rel="noopener noreferrer" className="underline decoration-line underline-offset-2 hover:decoration-ink2">
                  {n.titular}
                </a>
              </td>
              <td className="py-2 pr-4 whitespace-nowrap">{n.medio ?? '—'}</td>
              <td className="py-2 pr-4 whitespace-nowrap tabular-nums">{etiquetaFecha(n.fecha)}</td>
              <td className="py-2 pr-4 whitespace-nowrap">
                <span
                  className="mr-2 inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ background: n.tipo === 'Mención' ? 'var(--series-1)' : 'var(--series-2)' }}
                  aria-hidden
                />
                {n.tipo}
                {n.tipo === 'Réplica' && <span className="text-ink2"> · {n.medios_en_grupo} medios</span>}
              </td>
              <td className="py-2 pr-4 whitespace-nowrap">
                <span className="mr-1.5" style={{ color: SENT[n.sentimiento].color }} aria-hidden>
                  {SENT[n.sentimiento].glifo}
                </span>
                {n.sentimiento}
              </td>
              <td className="py-2 text-ink2">{n.via ? VIA[n.via] : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
