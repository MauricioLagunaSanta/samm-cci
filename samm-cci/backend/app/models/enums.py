import enum


class TipoRegistro(str, enum.Enum):
    """Clasificación exigida por el negocio (Fase 3 la calcula; Fase 2 deja SIN_CLASIFICAR)."""

    MENCION = "Mención"
    REPLICA = "Réplica"
    SIN_CLASIFICAR = "Sin clasificar"


class EstadoRelevancia(str, enum.Enum):
    """Resultado de la validación de relevancia (¿la nota realmente habla de la CCI?)."""

    PENDIENTE = "Pendiente"  # capturada, aún sin validar
    VALIDA = "Válida"
    DESCARTADA = "Descartada"  # se conserva en BD para auditoría; el dashboard no la cuenta
    REVISAR = "Revisar"  # ambigua o sin cuerpo: requiere ojo humano, nunca se descarta a ciegas


class Sentimiento(str, enum.Enum):
    POSITIVO = "Positivo"
    NEUTRO = "Neutro"
    NEGATIVO = "Negativo"


class FuenteOrigen(str, enum.Enum):
    GOOGLE_NEWS = "google_news"
    RSS_MEDIO = "rss_medio"
    BUSCADOR = "buscador"
    RED_SOCIAL = "red_social"
    MANUAL = "manual"
    HISTORICO = "historico"  # importada de los Excel mensuales hechos a mano (Fase 5)


class EstadoEjecucion(str, enum.Enum):
    EN_CURSO = "en_curso"
    OK = "ok"
    PARCIAL = "parcial"  # terminó, pero alguna consulta falló
    ERROR = "error"
