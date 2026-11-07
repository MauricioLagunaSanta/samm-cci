export interface Conteos {
  total: number
  menciones: number
  replicas: number
  positivas: number
  negativas: number
  neutras: number
}
export interface MesMetricas extends Conteos {
  mes: string
  por_revisar: number
}
export interface Mensual {
  provisional: boolean
  meses: MesMetricas[]
}
export interface Semana extends Conteos {
  semana_inicio: string
}
export interface Semanal {
  provisional: boolean
  semanas: Semana[]
}
export interface Resumen extends Conteos {
  mes: string
  por_revisar: number
  provisional: boolean
}
export interface Nota {
  id: number
  titular: string
  medio: string | null
  fecha: string
  url: string
  tipo: 'Mención' | 'Réplica'
  sentimiento: 'Positivo' | 'Neutro' | 'Negativo'
  via: 'entidad' | 'entidad_debil' | 'evento' | null
  medios_en_grupo: number
}

export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal })
  if (!r.ok) throw new Error(`La API respondió ${r.status} en ${url}`)
  return r.json() as Promise<T>
}

export interface ResultadoExport {
  archivo: string
  filas: number
  porRevisar: number
}

/** Descarga el Excel del mes y devuelve datos para informar a la persona. */
export async function descargarExcel(mes: string): Promise<ResultadoExport> {
  const r = await fetch(`/api/export/xlsx?mes=${encodeURIComponent(mes)}`)
  if (!r.ok) throw new Error(`No se pudo generar el Excel (${r.status})`)
  const blob = await r.blob()
  const archivo = `Monitoreo_de_Medios_${mes}.xlsx`
  const enlace = document.createElement('a')
  enlace.href = URL.createObjectURL(blob)
  enlace.download = archivo
  enlace.click()
  URL.revokeObjectURL(enlace.href)
  return {
    archivo,
    filas: Number(r.headers.get('X-Filas') ?? 0),
    porRevisar: Number(r.headers.get('X-Por-Revisar') ?? 0),
  }
}

export interface Exportacion {
  nombre: string
  mes: string
  generado: string // ISO local, p. ej. 2026-11-07T15:38:00
  filas: number
  bytes: number
}
