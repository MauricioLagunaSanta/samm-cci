"""Fase 5: columnas de la plantilla manual (tipo de contenido, redes, observaciones, archivo de origen).

El valor nuevo FuenteOrigen.HISTORICO no requiere DDL en SQLite (el enum se guarda como texto).

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":  # por si algún día se migra a PostgreSQL
        op.execute("ALTER TYPE fuenteorigen ADD VALUE IF NOT EXISTS 'HISTORICO'")
    with op.batch_alter_table("menciones") as batch:
        batch.add_column(sa.Column("tipo_contenido", sa.String(120)))
        batch.add_column(sa.Column("redes", sa.String(80)))
        batch.add_column(sa.Column("observaciones", sa.Text))
        batch.add_column(sa.Column("archivo_origen", sa.String(200)))


def downgrade() -> None:
    with op.batch_alter_table("menciones") as batch:
        for col in ("archivo_origen", "observaciones", "redes", "tipo_contenido"):
            batch.drop_column(col)
