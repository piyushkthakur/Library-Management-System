import sqlalchemy as sa
from alembic import op

revision = "0004_teachers"
down_revision = "0003_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teachers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("contact_number", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contact_number", name="uq_teachers_contact"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_teachers_active", "teachers", ["is_active"], unique=False)
    op.create_table(
        "teacher_issues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ISSUED", "RETURNED", name="teacherissuestatus"),
            nullable=False,
        ),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=False),
        sa.Column("returned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("active_teacher_lock", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("due_date >= issue_date", name="chk_tissue_due_after_issue"),
        sa.CheckConstraint(
            "return_date IS NULL OR return_date >= issue_date",
            name="chk_tissue_return_after_issue",
        ),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], onupdate="CASCADE", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["teachers.id"], onupdate="CASCADE", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["issued_by_user_id"], ["users.id"], onupdate="CASCADE", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["returned_by_user_id"],
            ["users.id"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "book_id", "active_teacher_lock", name="uq_tissue_active_teacher"
        ),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_tissue_teacher", "teacher_issues", ["teacher_id"], unique=False)
    op.create_index("ix_tissue_status", "teacher_issues", ["status"], unique=False)
    op.create_index(
        "ix_tissue_issue_date", "teacher_issues", ["issue_date"], unique=False
    )


def downgrade() -> None:
    op.drop_table("teacher_issues")
    op.drop_table("teachers")
    sa.Enum(name="teacherissuestatus").drop(op.get_bind(), checkfirst=True)
