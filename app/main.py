"""Composition root for the desktop Flet application.

The only place where services and repositories are constructed (dependency
injection per the Presentation Architecture Review). Entry point:

    flet run app/main.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

import flet as ft
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import load_environment
from app.core.database import Database, _find_xampp_root
from app.core.exceptions import LmsError
from app.core.security import SessionContext
from app.core.session_store import clear_session, load_session, save_session
from app.models.user import UserRole
from app.presentation.screens.auth.auth_screen import (
    AdminRegistrationScreen,
    ForgotPasswordScreen,
    LoginScreen,
    ResetPasswordScreen,
)
from app.presentation.screens.books.books_screen import BooksScreen
from app.presentation.screens.categories.categories_screen import CategoriesScreen
from app.presentation.screens.dashboard.dashboard_screen import DashboardScreen
from app.presentation.screens.librarians.librarians_screen import LibrariansScreen
from app.presentation.screens.my_activity.my_activity_screen import MyActivityScreen
from app.presentation.screens.reports.reports_screen import ReportsScreen
from app.presentation.screens.settings.settings_screen import SettingsScreen
from app.presentation.screens.teachers.teacher_issues_screen import TeacherIssuesScreen
from app.presentation.screens.teachers.teachers_screen import TeachersScreen
from app.presentation.screens.transactions.transactions_screen import TransactionsScreen
from app.presentation.shared_components.dialogs import info
from app.presentation.shared_components.errors import friendly_message
from app.presentation.shared_components.shell import Header, NotificationDialog, Sidebar
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import COLOR_SURFACE_ALT
from app.reporting import ExcelExporter, PdfExporter
from app.repositories import (
    BookRepository,
    CategoryRepository,
    OtpRepository,
    SettingsRepository,
    TeacherIssueRepository,
    TeacherRepository,
    TransactionRepository,
    UserRepository,
)
from app.services.auth_service import AuthService
from app.services.book_service import BookService
from app.services.category_service import CategoryService
from app.services.dashboard_service import DashboardService
from app.services.import_service import BookImportService
from app.services.librarian_service import LibrarianService
from app.services.notification_service import NotificationService
from app.services.report_service import ReportService
from app.services.settings_service import SettingsService
from app.services.teacher_issue_service import TeacherIssueService
from app.services.teacher_service import TeacherService
from app.services.transaction_service import TransactionService
from app.utils.validators import is_valid_isbn, normalize_isbn

NAV = {
    "dashboard": ("Dashboard", ft.Icons.SPACE_DASHBOARD),
    "books": ("Book Catalog", ft.Icons.MENU_BOOK),
    "categories": ("Categories", ft.Icons.LABEL_OUTLINE),
    "transactions": ("Issued/Returned Books", ft.Icons.RECEIPT_LONG),
    "teacher_issues": ("Teachers", ft.Icons.SCHOOL),
    "reports": ("Reports", ft.Icons.BAR_CHART),
    "my_activity": ("My Activity", ft.Icons.HISTORY),
    "librarians": ("Librarians", ft.Icons.GROUP),
    "settings": ("Settings", ft.Icons.SETTINGS_OUTLINED),
}

MODULES = list(NAV.keys())
ADMIN_ONLY = {"librarians", "settings"}
ADMIN_EXCLUDE = {"my_activity"}


def _classify_search(term: str) -> str:
    """Route a global search term: "books" for ISBN-shaped input, "transactions"
    for other all-digit input (contact numbers), "text" for the rest
    (titles, names, shelf codes — decided by hit counts at call time)."""
    digits = normalize_isbn(term)
    if digits.isdigit():
        if len(digits) in (10, 13) and is_valid_isbn(digits):
            return "books"
        return "transactions"
    return "text"


def _nav_items(role: str):
    if role == UserRole.ADMINISTRATOR:
        return [(icon, label, key, None) for key, (label, icon) in NAV.items() if key not in ADMIN_EXCLUDE]
    return [(icon, label, key, None) for key, (label, icon) in NAV.items() if key not in ADMIN_ONLY]


class _MainWindow:
    """Owns the auth flow and the authenticated shell."""

    def __init__(self, page: ft.Page, services: dict, toasts: ToastHost) -> None:
        self._page = page
        self._services = services
        self._toasts = toasts
        self._session: SessionContext | None = None
        self._screens: dict = {}
        # ponytail: built roots are cached with their screens and re-attached
        # on revisit. Rebuilding per visit re-parents the screens' __init__
        # controls under a fresh root, leaving stale parents behind — the
        # next control.update() then raises "must be added to the page".
        self._roots: dict = {}
        self._current_key: str | None = None
        self._width = getattr(page, "width", None) or 1360
        page.on_resize = self._resize
        self.root = ft.Container(bgcolor=COLOR_SURFACE_ALT, expand=True)
        self.sidebar: Sidebar | None = None
        self.header: Header | None = None
        self._content = ft.Container(
            expand=True,
            bgcolor=COLOR_SURFACE_ALT,
            padding=ft.Padding.symmetric(horizontal=32, vertical=20),
        )

    def show(self) -> ft.Container:
        return self.root

    # -- auth phase ---------------------------------------------------------------

    def _show_login(self) -> None:
        login_screen = LoginScreen(
            self._page, self._services["auth"], self._on_login, self._goto_forgot, self._goto_register
        )
        self._set_view(login_screen.build())
        login_screen.on_activate()

    def _goto_register(self) -> None:
        reg = AdminRegistrationScreen(self._page, self._services["auth"], self._show_login)
        self._set_view(reg.build())

    def _goto_forgot(self) -> None:
        forgot = ForgotPasswordScreen(
            self._page, self._services["auth"], self._show_login, self._goto_reset
        )
        self._set_view(forgot.build())

    def _goto_reset(self, email: str) -> None:
        reset = ResetPasswordScreen(
            self._page, self._services["auth"], email, self._show_login, self._show_login
        )
        self._set_view(reset.build())

    def _on_login(self, context: SessionContext) -> None:
        self._session = context
        save_session(context)
        self._build_shell()
        self.navigate("dashboard")

    # -- shell phase ----------------------------------------------------------------

    def _build_shell(self) -> None:
        self.sidebar = Sidebar(_nav_items(self._session.role), self.navigate, self._resize)
        self.header = Header(
            self._page,
            user_name=self._session.full_name,
            user_role=self._session.role,
            user_email=self._session.email,
            on_global_search=self._global_search,
            on_global_search_clear=self._clear_global_search,
            on_notifications=self._show_notifications,
            on_profile=self._show_profile,
            on_logout=self._logout,
        )
        content = ft.Column(
            [self.header, self._content],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
        )
        self.root.content = ft.Stack(
            [
                ft.Row(
                    [self.sidebar, content],
                    expand=True,
                    spacing=0,
                ),
                ft.Container(
                    content=self.header.dropdown,
                    top=56,
                    right=24,
                ),
                self._toasts.stack,
            ],
            expand=True,
            clip_behavior=ft.ClipBehavior.NONE,
        )
        self._resize()
        self._toasts.bind(self._page)
        self._notification_dialog = NotificationDialog(
            self._page, lambda: self._show_notifications(refresh=True), self._on_notification_action
        )

    def _resize(self, e=None) -> None:
        self._width = getattr(e, "width", None) or getattr(self._page, "width", None) or self._width
        if self._session is None or self.sidebar is None or self.header is None:
            return
        self.sidebar.resize(self._width)
        content_width = self._width - self.sidebar.width
        self.header.resize(content_width)
        self._content.padding = ft.Padding.symmetric(
            horizontal=16 if content_width < 900 else 32, vertical=20
        )
        self._toasts.resize(content_width)
        self._page.update()

    def navigate(self, key: str, params: dict | None = None) -> None:
        if self._session.role == UserRole.ADMINISTRATOR:
            allowed = {m: (label, icon) for m, (label, icon) in NAV.items() if m not in ADMIN_EXCLUDE}
        else:
            allowed = {m: (label, icon) for m, (label, icon) in NAV.items() if m not in ADMIN_ONLY}
        # ponytail: "teachers" is a hidden registry route under Teacher
        # Issues (no sidebar entry); keep the parent highlighted.
        if key not in allowed and key != "teachers":
            return
        self._toasts.clear()
        self.header.dropdown.visible = False
        self.sidebar.select("teacher_issues" if key == "teachers" else key)
        screen = self._screens.get(key)
        if screen is None:
            screen = self._make_screen(key)
            self._screens[key] = screen
            self._roots[key] = screen.build()
        self._content.content = self._roots[key]
        self._refresh_notifications()
        self._page.update()
        self._current_key = key
        screen.activate(params)

    def _refresh_notifications(self) -> None:
        context = self._session
        if context is None:
            return
        try:
            self._services["notifications"].refresh(context)
            count = self._services["notifications"].unread_count(context)
        except (LmsError, SQLAlchemyError) as exc:
            self._toasts.show(friendly_message(exc), "error")
            return
        self.header.set_unread_count(count)

    def _make_screen(self, key: str):
        c = self._services
        s = self._session
        toasts = self._toasts
        if key == "dashboard":
            return DashboardScreen(
                self._page, c["dashboard"], s, toasts,
                lambda status: self.navigate("transactions", {"status": status}),
            )
        if key == "books":
            return BooksScreen(self._page, c["books"], c["categories"], c["import_books"], s, toasts)
        if key == "categories":
            return CategoriesScreen(self._page, c["categories"], s, toasts)
        if key == "transactions":
            return TransactionsScreen(self._page, c["transactions"], c["books"], s, toasts)
        if key == "teacher_issues":
            return TeacherIssuesScreen(
                self._page, c["teacher_issues"], c["teachers"], c["books"], s, toasts,
                on_manage_teachers=lambda: self.navigate("teachers"),
            )
        if key == "teachers":
            return TeachersScreen(
                self._page, c["teachers"], s, toasts,
                on_back=lambda: self.navigate("teacher_issues"),
            )
        if key == "librarians":
            return LibrariansScreen(self._page, c["librarians"], s, toasts)
        if key == "reports":
            return ReportsScreen(self._page, c["reports"], c["categories"], c["librarians"], s, toasts)
        if key == "my_activity":
            return MyActivityScreen(self._page, c["transactions"], s, toasts)
        if key == "settings":
            return SettingsScreen(self._page, c["settings"], s, toasts)
        raise ValueError(f"Unknown module {key}")

    # -- shell actions --------------------------------------------------------------

    def _global_search(self, term: str) -> None:
        term = (term or "").strip()
        if not term:
            return
        route = _classify_search(term)
        if route == "books":
            self.navigate("books", {"search": term})
            return
        if route == "transactions":
            self.navigate("transactions", {"borrower": term})
            return
        # text (titles, names, shelf codes, ...): books first, then
        # transactions, else stay put with a toast.
        try:
            _, book_hits = self._services["books"].search(term, None, 1, 1)
        except (LmsError, SQLAlchemyError) as exc:
            self._toasts.show(friendly_message(exc), "error")
            return
        if book_hits:
            self.navigate("books", {"search": term})
            return
        try:
            _, txn_hits = self._services["transactions"].list_transactions(
                borrower_search=term, page_size=1
            )
        except (LmsError, SQLAlchemyError) as exc:
            self._toasts.show(friendly_message(exc), "error")
            return
        if txn_hits:
            self._toasts.show(
                f"No books matched '{term}' — showing matching transactions.",
                "info",
            )
            self.navigate("transactions", {"borrower": term})
            return
        self._toasts.show(
            f"No books or transactions matched '{term}'.", "info"
        )

    def _clear_global_search(self) -> None:
        """Header search box emptied: drop applied terms everywhere and
        reload the visible tab with live data."""
        for key in ("books", "transactions"):
            screen = self._screens.get(key)
            if screen is not None:
                screen.clear_search()
        current = self._screens.get(self._current_key)
        if self._current_key in ("books", "transactions") and current is not None:
            current.activate()

    def _show_notifications(self, refresh: bool = True) -> None:
        context = self._session
        try:
            if refresh:
                self._services["notifications"].refresh(context)
            notifications = self._services["notifications"].list_notifications(context)
            count = self._services["notifications"].unread_count(context)
        except (LmsError, SQLAlchemyError) as exc:
            self._toasts.show(friendly_message(exc), "error")
            return
        self._notification_dialog.set_notifications(notifications, count)
        self.header.set_unread_count(count)
        if not self._notification_dialog.dialog.open:
            self._page.show_dialog(self._notification_dialog.dialog)
        self._page.update()

    def _on_notification_action(self, action: str, id: int | None = None) -> None:
        context = self._session
        notifications = self._services["notifications"]
        try:
            if action == "mark_all_read":
                notifications.mark_all_read(context)
            elif action == "mark_read":
                notifications.mark_read(context, id)
            elif action == "dismiss":
                notifications.dismiss(context, id)
        except (LmsError, SQLAlchemyError) as exc:
            self._notification_dialog.set_error(friendly_message(exc))
            self._notification_dialog.dialog.update()
            return
        self._show_notifications()

    def _show_profile(self) -> None:
        info(self._page, "My Profile", [
            f"Name: {self._session.full_name}",
            f"Email: {self._session.email}",
            f"Role: {'Administrator' if self._session.role == UserRole.ADMINISTRATOR else 'Librarian'}",
        ])

    def _logout(self) -> None:
        self._session = None
        self._screens.clear()
        self._roots.clear()
        self._current_key = None
        self._toasts.clear()
        clear_session()
        self._show_login()

    def _set_view(self, view: ft.Control) -> None:
        self.root.content = ft.Container(view, alignment=ft.Alignment.CENTER, expand=True, bgcolor=COLOR_SURFACE_ALT)
        self._page.update()


def _show_loading(page: ft.Page, text: str) -> None:
    """Display a centered loading spinner on the page."""
    page.controls.clear()
    page.add(
        ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(width=48, height=48, stroke_width=4, color=COLOR_SURFACE_ALT),
                    ft.Container(height=16),
                    ft.Text(text, size=16, color=COLOR_SURFACE_ALT, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
            bgcolor="#1F2A44",
        )
    )
    page.update()


_LOG_PATH = Path(__file__).resolve().parent.parent / "lms_shutdown.log"


def _log(msg: str) -> None:
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _cleanup():
    """Stop MySQL gracefully (mysqladmin shutdown / graceful SQL SHUTDOWN),
    fall back to killprocess.bat only if graceful fails; stop Apache gracefully."""
    import time
    from pathlib import Path
    xampp_root = _find_xampp_root()
    _log(f"cleanup called, xampp_root={xampp_root}")
    # 1. Graceful MySQL shutdown first (mysqladmin or SQL SHUTDOWN command)
    graceful_ok = False
    mysql_bin = xampp_root / "mysql" / "bin" if xampp_root else None
    if mysql_bin and mysql_bin.exists():
        for graceful_cmd in [
            [str(mysql_bin / "mysqladmin"), "-u", "root", "shutdown"],
            [str(mysql_bin / "mysql"), "-u", "root", "-e", "SHUTDOWN"],
        ]:
            try:
                result = subprocess.run(
                    graceful_cmd,
                    cwd=str(xampp_root),
                    capture_output=True,
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                _log(f"graceful cmd={graceful_cmd[0]} rc={result.returncode}")
                if result.returncode == 0:
                    graceful_ok = True
                    break
            except Exception as exc:
                _log(f"graceful cmd={graceful_cmd[0]} exc={exc}")
    # 2. Force-kill only if graceful didn't work; add brief wait for graceful to finish
    if not graceful_ok:
        _log("graceful failed, running killprocess fallback")
        time.sleep(1.5)
        if not xampp_root:
            _log("no xampp_root, returning")
            return
        for proc_name in ("mysqld.exe", "httpd.exe"):
            script = xampp_root / "killprocess.bat"
            if script.exists():
                try:
                    subprocess.run(
                        ["cmd", "/c", str(script), proc_name],
                        cwd=str(xampp_root),
                        capture_output=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    _log(f"killprocess ran for {proc_name}")
                except Exception as exc:
                    _log(f"killprocess exc for {proc_name}: {exc}")
    else:
        _log("graceful succeeded, skip force-kill")

def main(page: ft.Page) -> None:
    load_environment()
    page.title = "Library Management System"
    page.window.width = 1252
    page.window.height = 792
    page.window.min_width = 800
    page.window.min_height = 600
    page.bgcolor = COLOR_SURFACE_ALT
    page.padding = 0

    # Clean up MySQL/Apache when the user closes the window or the process exits
    import atexit
    atexit.register(_cleanup)
    page.on_close = lambda e: (_cleanup(), True)

    _show_loading(page, "Starting database, please wait...")

    import threading
    _db_result: dict = {"database": None, "error": None, "done": False}

    def _check_db():
        db = Database()
        try:
            db.ensure_connectivity()
            _db_result["database"] = db
        except Exception as exc:
            _db_result["error"] = exc
        _db_result["done"] = True

    threading.Thread(target=_check_db, daemon=True).start()

    async def _poll():
        while not _db_result["done"]:
            await asyncio.sleep(0.1)
        db = _db_result["database"]
        if db is None:
            _show_db_error(page)
            return
        _finish_startup(page, db)

    page.run_task(_poll)


def _show_db_error(page: ft.Page) -> None:
    page.controls.clear()
    page.add(
        ft.Container(
            ft.Column(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color="#C0362C"),
                    ft.Container(height=12),
                    ft.Text("Could not connect to the database.", size=18, weight=ft.FontWeight.W_600, color="#1D2939"),
                    ft.Container(height=8),
                    ft.Text("Please start MySQL manually and restart the app.", size=14, color="#667085"),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
            bgcolor=COLOR_SURFACE_ALT,
        )
    )
    page.update()


def _finish_startup(page: ft.Page, database) -> None:
    user_repo = UserRepository()
    otp_repo = OtpRepository()
    settings_repo = SettingsRepository()
    book_repo = BookRepository()
    category_repo = CategoryRepository()
    transaction_repo = TransactionRepository()
    teacher_repo = TeacherRepository()
    teacher_issue_repo = TeacherIssueRepository()

    services = {
        "auth": AuthService(database, user_repo, otp_repo, settings_repo),
        "books": BookService(database, book_repo, category_repo),
        "categories": CategoryService(database, category_repo),
        "import_books": BookImportService(database, book_repo, category_repo),
        "transactions": TransactionService(database, transaction_repo, book_repo, settings_repo),
        "teachers": TeacherService(database, teacher_repo),
        "teacher_issues": TeacherIssueService(
            database, teacher_issue_repo, teacher_repo, book_repo, settings_repo
        ),
        "librarians": LibrarianService(database, user_repo, settings_repo),
        "settings": SettingsService(database, settings_repo),
        "dashboard": DashboardService(database, transaction_repo, book_repo, category_repo),
        "reports": ReportService(database, transaction_repo, settings_repo, PdfExporter(), ExcelExporter()),
        "notifications": NotificationService(database.session_factory),
    }

    page.controls.clear()
    window = _MainWindow(page, services, ToastHost())
    page.add(window.show())

    saved = load_session(database)
    if saved:
        window._on_login(saved)
    else:
        window._show_login()


if __name__ == "__main__":
    ft.run(main)