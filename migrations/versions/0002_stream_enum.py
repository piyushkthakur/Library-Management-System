"""alter stream enum: XI/XII -> Science/Commerce/Humanities

Revision ID: 0002_stream_enum
Revises: 0001_baseline
Create Date: 2026-08-13
"""

from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002_stream_enum"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "transactions",
        "stream",
        existing_type=mysql.ENUM("XI", "XII"),
        type_=mysql.ENUM("SCIENCE", "COMMERCE", "HUMANITIES"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "transactions",
        "stream",
        existing_type=mysql.ENUM("SCIENCE", "COMMERCE", "HUMANITIES"),
        type_=mysql.ENUM("XI", "XII"),
        existing_nullable=False,
    )
