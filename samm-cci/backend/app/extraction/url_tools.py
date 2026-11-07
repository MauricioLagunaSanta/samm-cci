"""Utilidades de URL: canonicalización (deduplicación) y resolución de enlaces de Google News."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Parámetros de rastreo que no cambian el contenido de la página
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src",
    "amp", "outputType", "output",
}


def canonicalize_url(url: str) -> str:
    """Normaliza una URL para detectar duplicados: sin esquema/www/fragmento/rastreo."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k not in _TRACKING_KEYS and not k.startswith(_TRACKING_PREFIXES)
    ]
    query.sort()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(query), ""))


def domain_of(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def is_google_news_link(url: str) -> bool:
    return urlsplit(url).netloc.lower().endswith("news.google.com")


def resolve_google_news_url(url: str, interval: int | None = 1) -> str | None:
    """Intenta obtener la URL real del medio a partir del enlace de Google News.

    Usa el paquete gratuito `googlenewsdecoder` (instalación opcional). Devuelve None si el
    paquete no está instalado o si la resolución falla; el llamador conserva entonces el
    enlace de Google y marca el registro como `url_resuelta=False`.
    """
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        return None
    try:
        result = gnewsdecoder(url, interval=interval)
    except Exception:  # noqa: BLE001  (cualquier fallo de red/parseo => conservar enlace de Google)
        return None
    # googlenewsdecoder >= 0.2 devuelve {"success": bool, "decoded_url": str}; versiones
    # anteriores usaban la clave "status". Se aceptan ambas.
    if isinstance(result, dict) and (result.get("success") or result.get("status")):
        return result.get("decoded_url") or None
    return None
