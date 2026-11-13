"""Books ISBN primary key (user decision): drop books.id, make isbn the PK,
and repoint transactions/teacher_issues FKs at books.isbn.

Data-preserving: existing ISBNs are normalized (dashes/spaces stripped,
uppercased — the same normalize_isbn the app uses on write) and every
loan row is carried over to the new book_isbn column. The migration
aborts BEFORE any structural change if normalization would merge two
distinct rows or if a loan references a missing book.
"""

import sqlalchemy as sa
from alembic import op

from app.utils.validators import normalize_isbn

revision = "0005_book_isbn_pk"
down_revision = "0004_teachers"
branch_labels = None
depends_on = None


def _tissue_book_fk_name(conn) -> str | None:
    """0004 created the teacher_issues→books FK without a name, so MySQL
    auto-named it — look the real name up instead of guessing."""
    return conn.execute(
        sa.text(
            "SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'teacher_issues' "
            "AND REFERENCED_TABLE_NAME = 'books'"
        )
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # -- 1. normalize stored ISBNs (Python pass: check first, then write) ---
    rows = conn.execute(sa.text("SELECT id, isbn FROM books")).all()
    normalized = [(book_id, normalize_isbn(isbn or "")) for book_id, isbn in rows]
    seen: dict[str, list] = {}
    for book_id, isbn in normalized:
        seen.setdefault(isbn, []).append(book_id)
    conflicts = {isbn: ids for isbn, ids in seen.items() if len(ids) > 1}
    if conflicts:
        detail = "; ".join(
            f"{isbn} (book ids {ids})" for isbn, ids in sorted(conflicts.items())
        )
        raise RuntimeError(
            "Cannot migrate: normalization merges distinct books: " + detail
        )
    for book_id, isbn in normalized:
        conn.execute(
            sa.text("UPDATE books SET isbn = :isbn WHERE id = :id"),
            {"isbn": isbn, "id": book_id},
        )

    # -- 2. new book_isbn columns + backfill --------------------------------
    op.add_column("transactions", sa.Column("book_isbn", sa.String(20), nullable=True))
    conn.execute(
        sa.text(
            "UPDATE transactions t JOIN books b ON b.id = t.book_id "
            "SET t.book_isbn = b.isbn"
        )
    )
    orphan_txns = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM transactions t "
            "LEFT JOIN books b ON b.id = t.book_id WHERE b.id IS NULL"
        )
    ).scalar()
    if orphan_txns:
        raise RuntimeError(
            f"Cannot migrate: {orphan_txns} transactions reference missing books."
        )

    op.add_column(
        "teacher_issues", sa.Column("book_isbn", sa.String(20), nullable=True)
    )
    conn.execute(
        sa.text(
            "UPDATE teacher_issues ti JOIN books b ON b.id = ti.book_id "
            "SET ti.book_isbn = b.isbn"
        )
    )
    orphan_issues = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM teacher_issues ti "
            "LEFT JOIN books b ON b.id = ti.book_id WHERE b.id IS NULL"
        )
    ).scalar()
    if orphan_issues:
        raise RuntimeError(
            f"Cannot migrate: {orphan_issues} teacher issues reference missing books."
        )

    # -- 3. drop old FKs, uniques, indexes, columns --------------------------
    op.drop_constraint("fk_txn_book", "transactions", type_="foreignkey")
    op.drop_constraint("uq_txn_active_contact", "transactions", type_="unique")
    op.drop_index("idx_txn_book_id", table_name="transactions")
    op.drop_column("transactions", "book_id")

    tissue_fk = _tissue_book_fk_name(conn)
    if tissue_fk:
        op.drop_constraint(tissue_fk, "teacher_issues", type_="foreignkey")
    op.drop_constraint("uq_tissue_active_teacher", "teacher_issues", type_="unique")
    op.drop_column("teacher_issues", "book_id")

    # -- 4. books: drop id, isbn becomes the PK -------------------------------
    op.execute("ALTER TABLE books MODIFY id INT NOT NULL")
    op.execute("ALTER TABLE books DROP PRIMARY KEY, ADD PRIMARY KEY (isbn)")
    op.drop_column("books", "id")
    op.drop_constraint("uq_books_isbn", "books", type_="unique")

    # -- 5. new NOT NULL + uniques + indexes + FKs ------------------------------
    op.alter_column(
        "transactions", "book_isbn", existing_type=sa.String(20), nullable=False
    )
    op.create_unique_constraint(
        "uq_txn_active_contact",
        "transactions",
        ["book_isbn", "active_contact_lock"],
    )
    op.create_index("idx_txn_book_isbn", "transactions", ["book_isbn"], unique=False)
    op.create_foreign_key(
        "fk_txn_book",
        "transactions",
        "books",
        ["book_isbn"],
        ["isbn"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )

    op.alter_column(
        "teacher_issues", "book_isbn", existing_type=sa.String(20), nullable=False
    )
    op.create_unique_constraint(
        "uq_tissue_active_teacher",
        "teacher_issues",
        ["book_isbn", "active_teacher_lock"],
    )
    op.create_index(
        "ix_tissue_book_isbn", "teacher_issues", ["book_isbn"], unique=False
    )
    op.create_foreign_key(
        "fk_tissue_book",
        "teacher_issues",
        "books",
        ["book_isbn"],
        ["isbn"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    conn = op.get_bind()

    op.drop_constraint("fk_txn_book", "transactions", type_="foreignkey")
    op.drop_constraint("uq_txn_active_contact", "transactions", type_="unique")
    op.drop_index("idx_txn_book_isbn", table_name="transactions")
    op.drop_constraint("fk_tissue_book", "teacher_issues", type_="foreignkey")
    op.drop_constraint(
        "uq_tissue_active_teacher", "teacher_issues", type_="unique"
    )
    op.drop_index("ix_tissue_book_isbn", table_name="teacher_issues")

    op.add_column("books", sa.Column("id", sa.Integer(), autoincrement=True))
    op.execute("ALTER TABLE books DROP PRIMARY KEY, ADD PRIMARY KEY (id)")
    op.execute("ALTER TABLE books MODIFY id INT NOT NULL AUTO_INCREMENT")
    op.create_unique_constraint("uq_books_isbn", "books", ["isbn"])

    op.add_column("transactions", sa.Column("book_id", sa.Integer(), nullable=True))
    conn.execute(
        sa.text(
            "UPDATE transactions t JOIN books b ON b.isbn = t.book_isbn "
            "SET t.book_id = b.id"
        )
    )
    op.alter_column(
        "transactions", "book_id", existing_type=sa.Integer(), nullable=False
    )
    op.create_unique_constraint(
        "uq_txn_active_contact",
        "transactions",
        ["book_id", "active_contact_lock"],
    )
    op.create_index("idx_txn_book_id", "transactions", ["book_id"], unique=False)
    op.create_foreign_key(
        "fk_txn_book",
        "transactions",
        "books",
        ["book_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    op.drop_column("transactions", "book_isbn")

    op.add_column("teacher_issues", sa.Column("book_id", sa.Integer(), nullable=True))
    conn.execute(
        sa.text(
            "UPDATE teacher_issues ti JOIN books b ON b.isbn = ti.book_isbn "
            "SET ti.book_id = b.id"
        )
    )
    op.alter_column(
        "teacher_issues", "book_id", existing_type=sa.Integer(), nullable=False
    )
    op.create_unique_constraint(
        "uq_tissue_active_teacher",
        "teacher_issues",
        ["book_id", "active_teacher_lock"],
    )
    op.create_foreign_key(
        None,
        "teacher_issues",
        "books",
        ["book_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    op.drop_column("teacher_issues", "book_isbn")
