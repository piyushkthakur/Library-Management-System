"""Visual render harness: builds real screens/shell/dialogs into a real Flet
window and screenshots them for visual QA. Usage: python _visual_harness.py <target> <outdir> <delay_s>
"""
import os
import sys
import time

sys.path.insert(0, r"C:\Users\Piyush Kumar\Desktop\Personal\Projects\Library Management System")

from datetime import date, datetime, timedelta

import flet as ft
from PIL import ImageGrab

from app.core.security import SessionContext
from app.models.user import UserRole

ADMIN = SessionContext(user_id=63, role=UserRole.ADMINISTRATOR, full_name="Piyush Kumar", email="admin@lib.local")
LIB = SessionContext(user_id=2, role=UserRole.LIBRARIAN, full_name="Librarian One", email="lib@lib.local")

# ---------- rich fakes ----------
class O:
    def __init__(self, **k): self.__dict__.update(k)

def _dt(d): return datetime.combine(d, datetime.min.time())

CATS = [O(id=i, name=n, description=f"{n} descriptions for books in this category",
          book_count=10+i) for i, n in enumerate(["Fiction", "Non-Fiction", "Science", "History", "Biography", "Poetry"])]

def mk_book(i):
    return O(id=i, title=["The Great Gatsby", "Clean Code: A Handbook of Agile Software Craftsmanship",
                          "1984", "Sapiens: A Brief History of Humankind", "The Pragmatic Programmer",
                          "A Very Long Book Title That Might Overflow The Cell and Cause Layout Issues",
                          "Atomic Habits", "Thinking, Fast and Slow"][i % 8],
             author=["F. Scott Fitzgerald", "Robert C. Martin", "George Orwell", "Yuval Noah Harari",
                     "Hunt & Thomas", "Someone Long", "James Clear", "Daniel Kahneman"][i % 8],
             isbn=f"978-3-16-{i:08d}", category_name=CATS[i % 6].name,
             available_copies=(i % 3), total_copies=(i % 5)+1, shelf_location=f"{chr(65+i%5)}-{i%20}")

class CatSvc:
    def list_all(self, ctx): return CATS
    def create(self, p, ctx): return O(id=99)
    def update(self, id, p, ctx): return None
    def delete(self, id, ctx): return None

class BookSvc:
    def search(self, term, cat, page, size): return [mk_book(i) for i in range(min(page*size, 34))], 34
    def list_available(self, term, page, size): return [mk_book(i) for i in range(4)], 4
    def create(self, p, ctx): return O(id=99)
    def update(self, id, p, ctx): return O()
    def delete(self, id, ctx): return None
    def get_by_isbn(self, isbn): return mk_book(0)

def mk_txn(i):
    st = ["Issued", "Overdue", "Returned"][i % 3]
    return O(id=i+1, book_title=mk_book(i).title, student_name=[f"Student Number {i} Full Name Here",
        "Arjun Singh", "Priya Sharma", "Rohan Verma"][i % 4], contact_number=f"9{i:09d}",
        class_name="12", stream="XI" if i % 2 else "XII", section=chr(65+i % 6),
        issue_date=date(2026, 7, 20), due_date=date(2026, 8, 3) + timedelta(days=i % 5),
        return_date=(date(2026, 8, 1) if st == "Returned" else None),
        status=st, fine_amount=25.00 if st == "Returned" else (12.50 if st == "Overdue" else None))

class TxnSvc:
    def list_transactions(self, **kw): return [mk_txn(i) for i in range(min(kw.get("page",1)*kw.get("page_size",25), 31))], 31
    def list_own_activity(self, ctx, **kw): return [mk_txn(i) for i in range(8)], 8
    def issue_book(self, p, ctx): return O(book_title="B", student_name="S")
    def return_book(self, id, ctx): return O(fine_amount=12.5)

class LibSvc:
    def list_librarians(self, ctx, page=1, page_size=25):
        libs = [O(id=i, full_name=f"Lib Person {i}" if i else "Piyush Kumar",
                 email=f"l{i}@lib.local", created_at=datetime(2026,7,1+i),
                 is_active=bool(i % 2)) for i in range(9)]
        return libs, 9
    def create(self, ctx, p): return None
    def update(self, ctx, id, p): return None
    def set_active_status(self, ctx, id, a): return None

class SetSvc:
    def get_all(self, ctx): return {"loan_period_days":"14","fine_enabled":"true","fine_rate_per_day":"5.00","otp_expiry_minutes":"10","password_min_length":"8"}
    def update(self, ctx, ch): return None
    def update_smtp_credentials(self, ctx, a, p): return None
    def send_test_email(self, ctx): return None

class DashSvc:
    def get_dashboard(self):
        return O(total_books=1240, total_available_copies=856, active_transactions=312, overdue_transactions=17,
                 trend=[O(date=_dt(date(2026,7,1)+timedelta(days=d)), issued=(d*3)%19, returned=(d*2)%15) for d in range(30)],
                 category_distribution=[O(category_name=c.name, book_count=40+i*7) for i, c in enumerate(CATS)],
                 overdue_items=[O(book_title=mk_book(i).title, student_name=f"S{i}", days_overdue=(i % 9)+1) for i in range(4)])

class RepSvc:
    def generate_report(self, ctx, **kw):
        return O(report_type=kw.get("report_type","YEARLY"), start_date=date(2026,1,1), end_date=date(2026,8,5),
                 totals=O(issued=842, returned=655, overdue=38, fines=312.75),
                 rows=[O(date=date(2026,1+i%12,1), issued=60+i, returned=40+i, overdue=i%7, fines=(i*5.5)) for i in range(12)],
                 include_fines=True)
    def export(self, ctx, rep, fmt): return O(file_name=f"report.{fmt}", file_bytes=b"x")

class AuthSvc:
    def admin_exists(self): return True
    def login(self, e, p): return ADMIN
    def request_otp(self, email): return None

def services():
    return {"auth": AuthSvc(), "books": BookSvc(), "categories": CatSvc(), "transactions": TxnSvc(),
            "librarians": LibSvc(), "settings": SetSvc(), "dashboard": DashSvc(), "reports": RepSvc()}

# ---------- render ----------
def shot(page, out, delay):
    page.window.left = 40; page.window.top = 40
    page.window.width = 1360; page.window.height = 860
    page.update()
    time.sleep(delay)
    img = ImageGrab.grab(bbox=(20, 20, 20 + 1360, 20 + 860))
    img.save(out)
    print("SAVED", out)

def render_shell(page, svc, screen_key=None, open_dialog=None):
    from app.main import _nav_items
    from app.presentation.shared_components.shell import Header, Sidebar
    from app.presentation.shared_components.toast import ToastHost
    toasts = ToastHost()
    items = _nav_items(UserRole.ADMINISTRATOR)
    sidebar = Sidebar(items, lambda k: None)
    _mock_page = type("_MockPage", (), {"update": lambda self: None})()
    header = Header(_mock_page, user_name="Test User", user_role="administrator", user_email="test@example.com", on_global_search=lambda t: None, on_notifications=lambda: None,
                    on_profile=lambda: None, on_logout=lambda: None)
    content = ft.Container(expand=True, bgcolor="#F2F4F7")
    if screen_key == "dashboard":
        from app.presentation.screens.dashboard.dashboard_screen import DashboardScreen
        scr = DashboardScreen(page, svc["dashboard"], ADMIN, toasts, lambda s: None)
        content.content = scr.build(); 
    elif screen_key == "books":
        from app.presentation.screens.books.books_screen import BooksScreen
        scr = BooksScreen(page, svc["books"], svc["categories"], ADMIN, toasts)
        content.content = scr.build(); 
    elif screen_key == "categories":
        from app.presentation.screens.categories.categories_screen import (
            CategoriesScreen,
        )
        scr = CategoriesScreen(page, svc["categories"], ADMIN, toasts)
        content.content = scr.build(); 
    elif screen_key == "transactions":
        from app.presentation.screens.transactions.transactions_screen import (
            TransactionsScreen,
        )
        scr = TransactionsScreen(page, svc["transactions"], svc["books"], ADMIN, toasts)
        content.content = scr.build(); 
    elif screen_key == "librarians":
        from app.presentation.screens.librarians.librarians_screen import (
            LibrariansScreen,
        )
        scr = LibrariansScreen(page, svc["librarians"], ADMIN, toasts)
        content.content = scr.build(); 
    elif screen_key == "reports":
        from app.presentation.screens.reports.reports_screen import ReportsScreen
        scr = ReportsScreen(page, svc["reports"], svc["categories"], svc["librarians"], ADMIN, toasts)
        content.content = scr.build(); 
    elif screen_key == "my_activity":
        from app.presentation.screens.my_activity.my_activity_screen import (
            MyActivityScreen,
        )
        scr = MyActivityScreen(page, svc["transactions"], ADMIN, toasts)
        content.content = scr.build(); 
    elif screen_key == "settings":
        from app.presentation.screens.settings.settings_screen import SettingsScreen
        scr = SettingsScreen(page, svc["settings"], ADMIN, toasts)
        content.content = scr.build(); 
    col = ft.Column([header, content], spacing=0, expand=True)
    root = ft.Stack([ft.Row([sidebar, col], expand=True), toasts.stack])
    toasts.stack.margin = ft.Margin.only(top=64, right=16)
    page.add(root)
    page.update()
    if screen_key:
        scr.activate()
    if screen_key == "dashboard":
        toasts.show("Welcome back, Piyush Kumar.", "success")
        toasts.show("3 books are overdue today.", "warning")
    if open_dialog == "add_book":
        scr._open_add_dialog()
    elif open_dialog == "delete":
        scr._confirm_delete(mk_book(1))
    elif open_dialog == "receipt":
        scr._show_receipt(mk_txn(0))
    elif open_dialog == "qr":
        scr._show_qr(mk_book(1))
    elif open_dialog == "return":
        scr._confirm_return(mk_txn(0))
    page.update()

def render_login(page):
    from app.presentation.screens.auth.auth_screen import LoginScreen
    s = LoginScreen(page, AuthSvc(), lambda c: None, lambda: None, lambda: None)
    page.add(s.build()); s.on_activate()
    page.update()

def render_dialog_only(page, kind):
    svc = services()
    from app.presentation.shared_components.toast import ToastHost
    toasts = ToastHost()
    page.add(ft.Container(expand=True, bgcolor="#F2F4F7"))
    page.update()
    if kind == "add_book":
        from app.presentation.screens.books.books_screen import BooksScreen
        scr = BooksScreen(page, svc["books"], svc["categories"], ADMIN, toasts)
        scr.build(); scr._open_add_dialog()
    elif kind == "delete":
        from app.presentation.screens.books.books_screen import BooksScreen
        scr = BooksScreen(page, svc["books"], svc["categories"], ADMIN, toasts)
        scr.build(); scr._confirm_delete(mk_book(1))
    elif kind == "qr":
        from app.presentation.screens.books.books_screen import BooksScreen
        scr = BooksScreen(page, svc["books"], svc["categories"], ADMIN, toasts)
        scr.build(); scr._show_qr(mk_book(1))
    elif kind == "datepicker":
        from app.presentation.shared_components.form_controls import DateField
        df = DateField(page, "From Date")
        df._open_picker(None)
    elif kind == "issue":
        from app.presentation.screens.transactions.transactions_screen import (
            TransactionsScreen,
        )
        t = TransactionsScreen(page, svc["transactions"], svc["books"], ADMIN, toasts)
        t.build(); t._open_issue_dialog()
    elif kind == "toasts":
        page.add(toasts.stack); toasts.stack.margin = ft.Margin.only(top=64, right=16)
        page.update()
        toasts.show("Book 'Clean Code' added successfully.", "success")
        toasts.show("A borrower is 5 days overdue.", "warning")
        toasts.show("Could not save. Try again.", "error")
    page.update()

def render_small_shell(page, out):
    page.window.width = 1000; page.window.height = 640
    page.window.left = 40; page.window.top = 40
    from app.main import _nav_items
    from app.models.user import UserRole
    from app.presentation.shared_components.shell import Header, Sidebar
    from app.presentation.shared_components.toast import ToastHost
    toasts = ToastHost()
    sidebar = Sidebar(_nav_items(UserRole.ADMINISTRATOR), lambda k: None)
    _mock_page = type("_MockPage", (), {"update": lambda self: None})()
    header = Header(_mock_page, user_name="Test User", user_role="administrator", user_email="test@example.com", on_global_search=lambda t: None, on_notifications=lambda: None,
                    on_profile=lambda: None, on_logout=lambda: None)
    from app.presentation.screens.books.books_screen import BooksScreen
    scr = BooksScreen(page, BookSvc(), CatSvc(), ADMIN, toasts)
    content = ft.Container(scr.build(), expand=True, bgcolor="#F2F4F7")
    col = ft.Column([header, content], spacing=0, expand=True)
    page.add(ft.Stack([sidebar, col]))
    page.update()
    
    time.sleep(2)
    img = ImageGrab.grab(bbox=(20, 20, 20 + 1000, 20 + 640))
    img.save(out)
    print("SAVED", out)

def main(page: ft.Page):
    target = os.environ.get("LMS_TARGET") or (sys.argv[1] if len(sys.argv) > 1 else "login")
    out = os.environ.get("LMS_OUT") or (sys.argv[2] if len(sys.argv) > 2 else "shot.png")
    delay = float(os.environ.get("LMS_DELAY", "2.0")) if os.environ.get("LMS_DELAY") else (float(sys.argv[3]) if len(sys.argv) > 3 else 2.0)
    page.title = "LMS QA"
    page.padding = 0
    page.bgcolor = "#F2F4F7"
    page.window.width = 1360; page.window.height = 860
    page.theme_mode = ft.ThemeMode.LIGHT
    try:
        if target == "login":
            render_login(page); shot(page, out, delay)
        elif target == "small_shell":
            render_small_shell(page, out)
        elif target in ("add_book", "delete", "qr", "datepicker", "issue", "toasts"):
            render_dialog_only(page, target); shot(page, out, delay)
        else:
            render_shell(page, services(), screen_key=target); shot(page, out, delay)
    except Exception:
        import traceback; traceback.print_exc()
    finally:
        time.sleep(0.5)
        try:
            page.window.close()
        except Exception:
            pass
        os._exit(0)

if __name__ == "__main__":
    ft.run(main=main)
