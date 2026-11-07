const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const MESES_LARGOS = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]

/** '2026-10' -> 'oct 2026' */
export function etiquetaMes(mes: string): string {
  const [y, m] = mes.split('-').map(Number)
  return `${MESES_CORTOS[m - 1]} ${y}`
}

/** '2026-10' -> 'octubre 2026' */
export function nombreMes(mes: string): string {
  const [y, m] = mes.split('-').map(Number)
  return `${MESES_LARGOS[m - 1]} ${y}`
}

/** '2026-10-12' -> '12 oct 2026' (sin pasar por Date: evita desfases de zona horaria) */
export function etiquetaFecha(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MESES_CORTOS[m - 1]} ${y}`
}

/** '2026-10-05' (lunes) -> 'sem. 5 oct' */
export function etiquetaSemana(iso: string): string {
  const [, m, d] = iso.split('-').map(Number)
  return `sem. ${d} ${MESES_CORTOS[m - 1]}`
}

export const numero = (n: number) => n.toLocaleString('es-CO')
