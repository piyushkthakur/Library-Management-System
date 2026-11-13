"""CategoryRepository — categories aggregate root (Volume 3, Chapter 12;
Volume 4, Chapter 10)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.category import Category
from app.repositories.base import BaseRepository
from app.repositories.interfaces import CategoryRepositoryInterface


class CategoryRepository(BaseRepository, CategoryRepositoryInterface):
    """Data access for the categories table."""

    def get_by_id(self, session: Session, category_id: int) -> Category | None:
        try:
            return session.get(Category, category_id)
        except Exception as error:
            raise self._translate(error)

    def get_by_name(self, session: Session, name: str) -> Category | None:
        try:
            return session.scalar(
                select(Category).where(
                    func.lower(Category.name) == name.strip().lower()
                )
            )
        except Exception as error:
            raise self._translate(error)

    def list_all(self, session: Session) -> list[Category]:
        try:
            return list(session.scalars(select(Category).order_by(Category.name)))
        except Exception as error:
            raise self._translate(error)

    def count_books_in_category(self, session: Session, category_id: int) -> int:
        try:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(Book)
                    .where(Book.category_id == category_id)
                )
                or 0
            )
        except Exception as error:
            raise self._translate(error)

    def count_books_per_category(self, session: Session) -> dict[int, int]:
        try:
            rows = session.execute(
                select(Book.category_id, func.count())
                .where(Book.category_id.isnot(None))
                .group_by(Book.category_id)
            ).all()
            return {row[0]: row[1] for row in rows}
        except Exception as error:
            raise self._translate(error)

    def create(self, session: Session, name: str, description: str | None) -> Category:
        try:
            category = Category(name=name.strip(), description=description)
            session.add(category)
            session.flush()
            return category
        except Exception as error:
            raise self._translate(error)

    def update(self, session: Session, category: Category) -> None:
        try:
            session.flush()
        except Exception as error:
            raise self._translate(error)

    def delete(self, session: Session, category_id: int) -> None:
        try:
            category = session.get(Category, category_id)
            if category is not None:
                session.delete(category)
                session.flush()
        except Exception as error:
            raise self._translate(error)
