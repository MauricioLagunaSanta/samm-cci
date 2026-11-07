from datetime import UTC, date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import (
    EstadoEjecucion,
    EstadoRelevancia,
    FuenteOrigen,
    Sentimiento,
    TipoRegistro,
)

__all__ = [
    "Base",
    "Boletin",
    "Ejecucion",
    "EstadoEjecucion",
    "EstadoRelevancia",
    "FuenteOrigen",
    "Mencion",
    "Sentimiento",
    "TipoRegistro",
]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Boletin(Base):
    """Comunicado enviado a prensa por la CCI. Base para detectar réplicas (Fase 3)."""

    __tablename__ = "boletines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titular: Mapped[str] = mapped_column(String(500))
    texto: Mapped[str] = mapped_column(Text, default="")
    fecha_envio: Mapped[date] = mapped_column(Date, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    menciones: Mapped[list["Mencion"]] = relationship(back_populates="boletin")


class Ejecucion(Base):
    """Bitácora de cada corrida del motor de extracción (auditoría y depuración)."""

    __tablename__ = "ejecuciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[EstadoEjecucion] = mapped_column(
        Enum(EstadoEjecucion), default=EstadoEjecucion.EN_CURSO
    )
    consultas: Mapped[int] = mapped_column(Integer, default=0)
    encontrados: Mapped[int] = mapped_column(Integer, default=0)
    nuevos: Mapped[int] = mapped_column(Integer, default=0)
    duplicados: Mapped[int] = mapped_column(Integer, default=0)
    descartados: Mapped[int] = mapped_column(Integer, default=0)
    errores: Mapped[str] = mapped_column(Text, default="")

    menciones: Mapped[list["Mencion"]] = relationship(back_populates="ejecucion")


class Mencion(Base):
    """Una nota/publicación encontrada. Titular y URL son obligatorios por requisito."""

    __tablename__ = "menciones"
    __table_args__ = (
        UniqueConstraint("url_canonica", name="uq_mencion_url_canonica"),
        Index("ix_mencion_fecha_tipo", "fecha_monitoreo", "tipo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Datos obligatorios del requisito ---
    titular: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)  # mejor URL disponible (real si se resolvió)

    # --- Trazabilidad de la URL ---
    url_google: Mapped[str | None] = mapped_column(Text)  # enlace de redirección de Google News
    url_canonica: Mapped[str] = mapped_column(String(1000))  # clave de deduplicación
    url_resuelta: Mapped[bool] = mapped_column(default=False)

    # --- Metadatos ---
    medio: Mapped[str | None] = mapped_column(String(200))
    dominio: Mapped[str | None] = mapped_column(String(255), index=True)
    resumen: Mapped[str | None] = mapped_column(Text)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fecha_captura: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Día de monitoreo (hora de Colombia) al que pertenece el registro: base del dashboard diario
    fecha_monitoreo: Mapped[date] = mapped_column(Date, index=True)
    consulta: Mapped[str | None] = mapped_column(String(300))
    origen: Mapped[FuenteOrigen] = mapped_column(
        Enum(FuenteOrigen), default=FuenteOrigen.GOOGLE_NEWS
    )

    # --- Cuerpo de la nota y validación de relevancia (Fase 3) ---
    cuerpo: Mapped[str | None] = mapped_column(Text)
    cuerpo_ok: Mapped[bool] = mapped_column(default=False)
    error_cuerpo: Mapped[str | None] = mapped_column(String(300))
    estado_relevancia: Mapped[EstadoRelevancia] = mapped_column(
        Enum(EstadoRelevancia), default=EstadoRelevancia.PENDIENTE, index=True
    )
    via_relevancia: Mapped[str | None] = mapped_column(String(30))  # entidad | entidad_debil | evento
    motivo_relevancia: Mapped[str | None] = mapped_column(String(400))
    terminos_detectados: Mapped[str | None] = mapped_column(Text)  # separados por " | "
    fecha_validacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Clasificación Mención/Réplica (Fase 4) ---
    tipo: Mapped[TipoRegistro] = mapped_column(
        Enum(TipoRegistro), default=TipoRegistro.SIN_CLASIFICAR, index=True
    )
    score_similitud: Mapped[float | None] = mapped_column(Float)
    boletin_id: Mapped[int | None] = mapped_column(ForeignKey("boletines.id"))
    sentimiento: Mapped[Sentimiento | None] = mapped_column(Enum(Sentimiento))

    # --- Datos de la plantilla manual (Fase 5: histórico importado) ---
    tipo_contenido: Mapped[str | None] = mapped_column(String(120))  # FACEBOOK, PÁGINA WEB, RADIO...
    redes: Mapped[str | None] = mapped_column(String(80))  # redes marcadas, separadas por coma
    observaciones: Mapped[str | None] = mapped_column(Text)
    archivo_origen: Mapped[str | None] = mapped_column(String(200))  # archivo#hoja!fila de donde viene

    ejecucion_id: Mapped[int | None] = mapped_column(ForeignKey("ejecuciones.id"))

    boletin: Mapped[Boletin | None] = relationship(back_populates="menciones")
    ejecucion: Mapped[Ejecucion | None] = relationship(back_populates="menciones")
