import { useEffect, useState } from 'react'
import { getJson } from '../api'

interface Estado<T> {
  url: string | null // URL a la que corresponden los datos actuales
  data: T | null
  error: string | null
}

/**
 * Carga JSON. Al cambiar la URL conserva los datos anteriores (sin parpadeo ni salto de
 * diseño) y `cargando` es verdadero hasta que llegan los nuevos.
 */
export function useApi<T>(url: string | null, recargar = 0) {
  const [estado, setEstado] = useState<Estado<T>>({ url: null, data: null, error: null })

  useEffect(() => {
    if (url === null) return
    const ctl = new AbortController()
    getJson<T>(url, ctl.signal)
      .then((data) => setEstado({ url, data, error: null }))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === 'AbortError') return
        const mensaje = e instanceof Error ? e.message : String(e)
        setEstado((previo) => ({ url, data: previo.data, error: mensaje }))
      })
    return () => ctl.abort()
  }, [url, recargar])

  return { data: estado.data, error: estado.error, cargando: url !== null && estado.url !== url }
}
