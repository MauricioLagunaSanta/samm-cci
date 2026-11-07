import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { numero } from '../lib/format'

export interface Serie {
  clave: string
  nombre: string
  color: string // variable CSS, p. ej. 'var(--series-1)'
  glifo?: string // icono junto al nombre (para que el color no sea el único canal)
}

interface Props {
  datos: Record<string, string | number>[]
  xClave: string
  xFormato: (v: string) => string
  series: Serie[]
  seleccionado?: string
  onSelect?: (x: string) => void
  alto?: number
}

export function Leyenda({ series }: { series: Serie[] }) {
  return (
    <ul className="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink2">
      {series.map((s) => (
        <li key={s.clave} className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />
          {s.glifo && <span aria-hidden>{s.glifo}</span>}
          {s.nombre}
        </li>
      ))}
    </ul>
  )
}

interface TooltipProps {
  active?: boolean
  label?: string | number
  payload?: ReadonlyArray<{ dataKey?: string | number; value?: number | string }>
}

function Lectura({ active, payload, label, series, xFormato }: TooltipProps & { series: Serie[]; xFormato: (v: string) => string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm shadow-md">
      <div className="mb-1 text-ink2">{xFormato(String(label))}</div>
      {series.map((s) => {
        const v = payload.find((p) => p.dataKey === s.clave)?.value
        return (
          <div key={s.clave} className="flex items-center gap-2">
            <span className="inline-block h-0.5 w-3" style={{ background: s.color }} aria-hidden />
            <span className="font-semibold text-ink">{numero(Number(v ?? 0))}</span>
            <span className="text-ink2">{s.nombre}</span>
          </div>
        )
      })}
    </div>
  )
}

/** Barras agrupadas: máx. 24 px, extremo redondeado de 4 px, 2 px de separación, rejilla hairline. */
export function GroupedBars({ datos, xClave, xFormato, series, seleccionado, onSelect, alto = 260 }: Props) {
  return (
    <div className={onSelect ? 'selectable' : undefined} style={{ height: alto }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={datos} barGap={2} barCategoryGap="28%" margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" strokeWidth={1} />
          <XAxis
            dataKey={xClave}
            tickLine={false}
            axisLine={{ stroke: 'var(--baseline)' }}
            tick={({ x, y, payload }) => {
              const valor = String(payload?.value ?? '')
              const activo = valor === seleccionado
              return (
                <text
                  x={x}
                  y={Number(y ?? 0) + 14}
                  textAnchor="middle"
                  fontSize={12}
                  fontWeight={activo ? 600 : 400}
                  fill={activo ? 'var(--text-primary)' : 'var(--muted)'}
                >
                  {xFormato(valor)}
                </text>
              )
            }}
          />
          <YAxis
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 12, fill: 'var(--muted)' }}
          />
          <Tooltip
            cursor={{ fill: 'var(--wash)' }}
            content={(p) => <Lectura {...(p as TooltipProps)} series={series} xFormato={xFormato} />}
          />
          {series.map((s) => (
            <Bar
              key={s.clave}
              dataKey={s.clave}
              name={s.nombre}
              fill={s.color}
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
              isAnimationActive={false}
              onClick={(d) => {
                const x = (d as unknown as { payload?: Record<string, string> }).payload?.[xClave]
                if (x && onSelect) onSelect(x)
              }}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Gemela en tabla de una gráfica de barras agrupadas. */
export function TablaGemela({
  datos, xClave, xTitulo, xFormato, columnas,
}: {
  datos: Record<string, string | number>[]
  xClave: string
  xTitulo: string
  xFormato: (v: string) => string
  columnas: { clave: string; titulo: string }[]
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-ink2">
            <th className="py-2 pr-4 font-medium">{xTitulo}</th>
            {columnas.map((c) => (
              <th key={c.clave} className="py-2 pr-4 text-right font-medium">
                {c.titulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {datos.map((d) => (
            <tr key={String(d[xClave])} className="border-b border-line last:border-0">
              <td className="py-2 pr-4">{xFormato(String(d[xClave]))}</td>
              {columnas.map((c) => (
                <td key={c.clave} className="py-2 pr-4 text-right tabular-nums">
                  {numero(Number(d[c.clave] ?? 0))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
