import sqlalchemy as sa
from alembic import op

revision = "0003_notifications"
down_revision = "0002_stream_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_dismissed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_key", name="uq_notifications_user_event"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index(
        "ix_notifications_user_visible_created",
        "notifications",
        ["user_id", "is_dismissed", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("notifications")
