import type { Exportacion } from '../api'
import { etiquetaFecha, nombreMes } from '../lib/format'

function tamano(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** Lista de Excel que el sistema ya generó, con descarga directa. */
export function ExcelsGenerados({ items }: { items: Exportacion[] }) {
  if (!items.length) {
    return (
      <p className="text-sm text-ink2">
        Aún no has generado ningún Excel. Usa «Exportar a Excel» y quedará guardado aquí.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-ink2">
          <tr className="border-b border-line">
            <th className="py-2 pr-4 font-medium">Mes</th>
            <th className="py-2 pr-4 font-medium">Generado</th>
            <th className="py-2 pr-4 text-right font-medium">Filas</th>
            <th className="py-2 pr-4 text-right font-medium">Tamaño</th>
            <th className="py-2 font-medium">
              <span className="sr-only">Descargar</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.nombre} className="border-b border-line last:border-0">
              <td className="py-2 pr-4">{nombreMes(e.mes)}</td>
              <td className="py-2 pr-4 text-ink2">
                {etiquetaFecha(e.generado.slice(0, 10))} · {e.generado.slice(11, 16)}
              </td>
              <td className="py-2 pr-4 text-right tabular-nums">{e.filas}</td>
              <td className="py-2 pr-4 text-right tabular-nums text-ink2">{tamano(e.bytes)}</td>
              <td className="py-2 text-right">
                <a
                  href={`/api/exportaciones/${encodeURIComponent(e.nombre)}`}
                  download={e.nombre}
                  className="rounded-md border border-edge px-2.5 py-1 hover:bg-wash"
                >
                  Descargar
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
