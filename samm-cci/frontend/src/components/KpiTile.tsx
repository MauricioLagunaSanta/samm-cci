interface Props {
  etiqueta: string
  valor: number | string
  nota?: string
  delta?: { valor: number; contra: string }
}

export function KpiTile({ etiqueta, valor, nota, delta }: Props) {
  const signo = delta ? (delta.valor > 0 ? '▲' : delta.valor < 0 ? '▼' : '–') : ''
  return (
    <div className="rounded-xl border border-edge bg-surface p-4">
      <div className="text-sm text-ink2">{etiqueta}</div>
      <div className="mt-1 text-3xl font-semibold">{valor}</div>
      {delta && (
        <div className="mt-1 text-xs text-ink2">
          {signo} {Math.abs(delta.valor)} vs. {delta.contra}
        </div>
      )}
      {nota && <div className="mt-1 text-xs text-ink2">{nota}</div>}
    </div>
  )
}
