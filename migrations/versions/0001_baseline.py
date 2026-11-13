"""baseline schema: six tables + settings seeds

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            mysql.ENUM("ADMINISTRATOR", "LIBRARIAN"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("idx_users_role", "users", ["role"], unique=False)

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_categories_name"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )

    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("isbn", sa.String(length=20), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("total_copies", sa.Integer(), nullable=False),
        sa.Column("available_copies", sa.Integer(), nullable=False),
        sa.Column("shelf_location", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "available_copies <= total_copies", name="chk_books_copies_range"
        ),
        sa.CheckConstraint("available_copies >= 0", name="chk_books_copies_nonneg"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_books_category",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("isbn", name="uq_books_isbn"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("idx_books_category_id", "books", ["category_id"], unique=False)
    op.create_index("idx_books_title", "books", ["title"], unique=False)
    op.create_index("idx_books_author", "books", ["author"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("student_name", sa.String(length=150), nullable=False),
        sa.Column("contact_number", sa.String(length=20), nullable=False),
        sa.Column("class", sa.String(length=20), nullable=False),
        sa.Column(
            "stream",
            mysql.ENUM("SCIENCE", "COMMERCE", "HUMANITIES"),
            nullable=False,
        ),
        sa.Column("section", sa.String(length=10), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            mysql.ENUM("ISSUED", "RETURNED"),
            nullable=False,
            server_default="ISSUED",
        ),
        sa.Column("fine_amount", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=False),
        sa.Column("returned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("active_contact_lock", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("due_date >= issue_date", name="chk_txn_due_after_issue"),
        sa.CheckConstraint(
            "return_date IS NULL OR return_date >= issue_date",
            name="chk_txn_return_after_issue",
        ),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name="fk_txn_book",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issued_by_user_id"],
            ["users.id"],
            name="fk_txn_issued_by",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["returned_by_user_id"],
            ["users.id"],
            name="fk_txn_returned_by",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "book_id", "active_contact_lock", name="uq_txn_active_contact"
        ),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("idx_txn_book_id", "transactions", ["book_id"], unique=False)
    op.create_index(
        "idx_txn_contact_number", "transactions", ["contact_number"], unique=False
    )
    op.create_index("idx_txn_status", "transactions", ["status"], unique=False)
    op.create_index("idx_txn_issue_date", "transactions", ["issue_date"], unique=False)
    op.create_index("idx_txn_due_date", "transactions", ["due_date"], unique=False)
    op.create_index(
        "idx_txn_issued_by", "transactions", ["issued_by_user_id"], unique=False
    )

    op.create_table(
        "password_reset_otps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("otp_code_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_otp_user",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("idx_otp_user_id", "password_reset_otps", ["user_id"], unique=False)
    op.create_index(
        "idx_otp_expires_at", "password_reset_otps", ["expires_at"], unique=False
    )

    op.create_table(
        "settings",
        sa.Column("setting_key", sa.String(length=100), nullable=False),
        sa.Column("setting_value", sa.String(length=500), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("setting_key"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )

    settings_rows = [
        ("loan_period_days", "14"),
        ("fine_enabled", "false"),
        ("fine_rate_per_day", "0.00"),
        ("otp_expiry_minutes", "10"),
        ("smtp_host", "smtp.gmail.com"),
        ("smtp_port", "587"),
        ("password_min_length", "8"),
        ("login_max_attempts", "5"),
        ("login_lockout_minutes", "15"),
        ("login_window_minutes", "15"),
    ]
    op.bulk_insert(
        sa.table(
            "settings",
            sa.column("setting_key", sa.String()),
            sa.column("setting_value", sa.String()),
        ),
        [{"setting_key": k, "setting_value": v} for k, v in settings_rows],
    )


def downgrade() -> None:
    op.drop_table("password_reset_otps")
    op.drop_index("idx_txn_issued_by", table_name="transactions")
    op.drop_index("idx_txn_due_date", table_name="transactions")
    op.drop_index("idx_txn_issue_date", table_name="transactions")
    op.drop_index("idx_txn_status", table_name="transactions")
    op.drop_index("idx_txn_contact_number", table_name="transactions")
    op.drop_index("idx_txn_book_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("idx_books_author", table_name="books")
    op.drop_index("idx_books_title", table_name="books")
    op.drop_index("idx_books_category_id", table_name="books")
    op.drop_table("books")
    op.drop_table("categories")
    op.drop_index("idx_users_role", table_name="users")
    op.drop_table("users")
    op.drop_table("settings")
