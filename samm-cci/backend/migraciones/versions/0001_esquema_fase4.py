"""Esquema base (Fases 2-4): boletines, ejecuciones y menciones.

Las bases creadas antes de Alembic (con create_all) ya tienen este esquema: app.database.migrar()
las marca con 'stamp 0001' y aplica solo lo posterior.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "boletines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("titular", sa.String(500), nullable=False),
        sa.Column("texto", sa.Text, nullable=False),
        sa.Column("fecha_envio", sa.Date, nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_boletines_fecha_envio", "boletines", ["fecha_envio"])
    op.create_table(
        "ejecuciones",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True)),
        sa.Column("estado", sa.Enum("EN_CURSO", "OK", "PARCIAL", "ERROR", name="estadoejecucion"), nullable=False),
        sa.Column("consultas", sa.Integer, nullable=False),
        sa.Column("encontrados", sa.Integer, nullable=False),
        sa.Column("nuevos", sa.Integer, nullable=False),
        sa.Column("duplicados", sa.Integer, nullable=False),
        sa.Column("descartados", sa.Integer, nullable=False),
        sa.Column("errores", sa.Text, nullable=False),
    )
    op.create_table(
        "menciones",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("titular", sa.String(500), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("url_google", sa.Text),
        sa.Column("url_canonica", sa.String(1000), nullable=False),
        sa.Column("url_resuelta", sa.Boolean, nullable=False),
        sa.Column("medio", sa.String(200)),
        sa.Column("dominio", sa.String(255)),
        sa.Column("resumen", sa.Text),
        sa.Column("fecha_publicacion", sa.DateTime(timezone=True)),
        sa.Column("fecha_captura", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_monitoreo", sa.Date, nullable=False),
        sa.Column("consulta", sa.String(300)),
        sa.Column(
            "origen",
            sa.Enum("GOOGLE_NEWS", "RSS_MEDIO", "BUSCADOR", "RED_SOCIAL", "MANUAL", name="fuenteorigen"),
            nullable=False,
        ),
        sa.Column("cuerpo", sa.Text),
        sa.Column("cuerpo_ok", sa.Boolean, nullable=False),
        sa.Column("error_cuerpo", sa.String(300)),
        sa.Column(
            "estado_relevancia",
            sa.Enum("PENDIENTE", "VALIDA", "DESCARTADA", "REVISAR", name="estadorelevancia"),
            nullable=False,
        ),
        sa.Column("via_relevancia", sa.String(30)),
        sa.Column("motivo_relevancia", sa.String(400)),
        sa.Column("terminos_detectados", sa.Text),
        sa.Column("fecha_validacion", sa.DateTime(timezone=True)),
        sa.Column(
            "tipo", sa.Enum("MENCION", "REPLICA", "SIN_CLASIFICAR", name="tiporegistro"), nullable=False
        ),
        sa.Column("score_similitud", sa.Float),
        sa.Column("boletin_id", sa.Integer, sa.ForeignKey("boletines.id")),
        sa.Column("sentimiento", sa.Enum("POSITIVO", "NEUTRO", "NEGATIVO", name="sentimiento")),
        sa.Column("ejecucion_id", sa.Integer, sa.ForeignKey("ejecuciones.id")),
        sa.UniqueConstraint("url_canonica", name="uq_mencion_url_canonica"),
    )
    op.create_index("ix_menciones_dominio", "menciones", ["dominio"])
    op.create_index("ix_menciones_fecha_monitoreo", "menciones", ["fecha_monitoreo"])
    op.create_index("ix_menciones_estado_relevancia", "menciones", ["estado_relevancia"])
    op.create_index("ix_menciones_tipo", "menciones", ["tipo"])
    op.create_index("ix_mencion_fecha_tipo", "menciones", ["fecha_monitoreo", "tipo"])


def downgrade() -> None:
    op.drop_table("menciones")
    op.drop_table("ejecuciones")
    op.drop_table("boletines")
