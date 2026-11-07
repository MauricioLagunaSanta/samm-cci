"""Descarga una nota y extrae su cuerpo de texto con trafilatura."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import trafilatura

from app.config import get_settings

MIN_BODY_CHARS = 200  # menos que esto suele ser un muro de pago, un stub de JS o un error


@dataclass
class ArticleContent:
    ok: bool
    texto: str | None = None
    error: str | None = None


def extract_from_html(html: str, url: str | None = None) -> ArticleContent:
    """Extrae el cuerpo principal del HTML. Pura (sin red): se prueba offline."""
    texto = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=False, include_links=False
    )
    if not texto:
        return ArticleContent(False, None, "No se pudo extraer texto del HTML")
    if len(texto) < MIN_BODY_CHARS:
        return ArticleContent(False, texto, f"Cuerpo demasiado corto ({len(texto)} caracteres)")
    return ArticleContent(True, texto, None)


def make_client(timeout: float | None = None) -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        timeout=timeout or settings.http_timeout,
        headers={
            "User-Agent": settings.http_user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "es-CO,es;q=0.9",
        },
        follow_redirects=True,
    )


def fetch_article(url: str, client: httpx.Client, max_bytes: int = 2_000_000) -> ArticleContent:
    """Descarga `url` (solo http/https, solo HTML, con tope de tamaño) y extrae el cuerpo."""
    if urlsplit(url).scheme not in ("http", "https"):
        return ArticleContent(False, None, "Esquema de URL no permitido")
    try:
        with client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                return ArticleContent(False, None, f"HTTP {resp.status_code}")
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype.lower():
                return ArticleContent(False, None, f"Contenido no HTML ({ctype or 'desconocido'})")
            chunks, size = [], 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    return ArticleContent(False, None, "Página demasiado grande")
                chunks.append(chunk)
            html = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        return ArticleContent(False, None, f"Error de red: {type(exc).__name__}")
    return extract_from_html(html, url)
