"""Configuración central del backend (variables de entorno + sources.yaml)."""
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'samm.db').as_posix()}"
    sources_file: Path = BASE_DIR / "config" / "sources.yaml"
    http_timeout: float = 15.0
    http_user_agent: str = "SAMM-CCI/0.1 (monitoreo de medios; proyecto universitario)"
    # Pausa cortés entre peticiones, en segundos
    request_delay: float = 1.0
    # Excel real de "Monitoreo de Medios" para usar como plantilla al exportar (opcional)
    plantilla_xlsx: Path | None = None
    # Carpeta donde se guarda una copia de cada Excel generado desde la web
    exports_dir: Path = BASE_DIR / "data" / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_sources(path: Path | None = None) -> dict:
    """Lee consultas, ventana de búsqueda y demás parámetros de sources.yaml."""
    path = path or get_settings().sources_file
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
