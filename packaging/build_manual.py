"""Generate the LMS User Manual (.docx). Run: python packaging/build_manual.py"""
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = Path(__file__).resolve().parent.parent / "Library Management System - User Manual.docx"

doc = Document()
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(11)


def h(text, level=1):
    doc.add_heading(text, level=level)


def p(text, bold=False, italic=False):
    par = doc.add_paragraph()
    run = par.add_run(text)
    run.bold = bold
    run.italic = italic
    return par


def bullets(items):
    for it in items:
        doc.add_paragraph(it, style="List Bullet")


def steps(items):
    for it in items:
        doc.add_paragraph(it, style="List Number")


def table(headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    hdr = t.rows[0].cells
    for i, htext in enumerate(headers):
        hdr[i].text = ""
        run = hdr[i].paragraphs[0].add_run(htext)
        run.bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
    doc.add_paragraph()
    return t


# ---------------- Title page ----------------
title = doc.add_heading("Library Management System", level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run("User Manual — Library Management System\nVersion 1.0.0")
r.font.size = Pt(14)
r.bold = True
doc.add_paragraph()

# ---------------- 1. Introduction ----------------
h("1. Introduction", 1)
p("The Library Management System (LMS) is a desktop application for managing a school library: "
  "cataloguing books, issuing and returning them to students and teachers, tracking fines, "
  "and producing circulation reports. It runs on Windows and uses XAMPP (MySQL) for storage.")
h("1.1 Who uses this system", 2)
table(
    ["Role", "Can log in", "Access"],
    [
        ["Administrator", "Yes", "Everything, plus Settings, Librarians (staff accounts), and full Reports."],
        ["Librarian", "Yes", "Day-to-day work: books, categories, issues/returns, teachers, reports, My Activity. "
                             "Cannot change Settings or manage Librarians."],
        ["Students & Teachers", "No", "They are borrower records in the system, not login accounts."],
    ],
)
p("Screens appear or are hidden automatically based on the signed-in role. A librarian, for example, "
  "will not see Librarians or Settings in the sidebar at all.")

# ---------------- 2. Getting started ----------------
h("2. Getting Started", 1)
h("2.1 Starting the application", 2)
steps([
    "Make sure MySQL is available (XAMPP). The app checks the database on startup and shows "
    "\"Starting database, please wait...\" while it connects.",
    "Launch LibraryManagementSystem from the Desktop shortcut or Start Menu.",
    "If the database cannot be reached you will see \"Could not connect to the database. / "
    "Please start MySQL manually and restart the app.\" — start MySQL (XAMPP Control Panel) and reopen the app.",
])
h("2.2 First run — register the Administrator", 2)
p("No account exists on a fresh installation. The Sign In screen shows a \"Register administrator\" link "
  "(it is only visible while no administrator exists).")
steps([
    "Click \"Register administrator\".",
    "Fill Full Name, Email Address, Password and Confirm Password.",
    "Password rules: minimum 8 characters with at least one uppercase letter, one lowercase letter and one digit. "
    "(Examples: Library@2026, LibAdmin1.)",
    "Click \"Register Administrator\". You return to Sign In — sign in with the new account.",
])
p("After registering, create Librarian accounts from the Librarians screen (Administrator only). "
  "Each librarian receives a Temporary Password set by you; they can change it later via Forgot Password.")
h("2.3 Signing in", 2)
bullets([
    "Sign In screen: Email Address + Password, then \"Sign In\".",
    "If you stay signed in, the app remembers your session and skips the login next time. "
    "Use \"Sign Out\" (avatar menu, top-right) to switch users.",
    "Too many wrong passwords (5 failed attempts within 15 minutes by default) locks the login for "
    "15 minutes: \"Too many failed login attempts. Try again in N minute(s).\" Restarting the app clears the lock.",
    "Unknown email and wrong password both show \"Invalid email or password.\" — the app never reveals which one was wrong.",
])
h("2.4 Forgot password (OTP via email)", 2)
steps([
    "Click \"Forgot password?\" on the Sign In screen.",
    "Enter your Email Address and click \"Send OTP\". A 6-digit code is emailed to you "
    "(subject: \"Your LMS password reset code\").",
    "On the next screen enter the OTP Code, your New Password and confirm it, then click \"Reset Password\".",
    "The code expires after the OTP window (10 minutes by default) and can be used only once.",
])
p("Note: email must be configured by the Administrator (Settings → Email & OTP) before OTP emails are sent. "
  "For security, the app shows the same \"sent\" message even if the email address does not exist.")

# ---------------- 3. Navigating ----------------
h("3. Navigating the Application", 1)
h("3.1 Layout", 2)
bullets([
    "Sidebar (left): all modules available to your role. Click a module to open it; the current one is highlighted.",
    "Header (top): app title \"Library Management System\", a global search box, a notification bell (with unread badge), "
    "and your avatar menu (name, email, role, My Profile, Sign Out).",
    "The sidebar collapses to icons when the window is narrow; drag the window edges to resize (minimum 800×600).",
])
h("3.2 Modules in the sidebar", 2)
table(
    ["Sidebar item", "What it is for", "Who sees it"],
    [
        ["Dashboard", "Live overview: totals, charts, overdue books.", "Everyone"],
        ["Book Catalog", "All books: add, edit, delete, search, import from a file.", "Everyone"],
        ["Categories", "Manage book categories.", "Everyone"],
        ["Issued/Returned Books", "Student loans: issue, return, fines, receipts.", "Everyone"],
        ["Teachers", "Teacher book loans (issue/return) and the teacher registry.", "Everyone"],
        ["Reports", "Circulation and fine reports; export to PDF/Excel.", "Everyone"],
        ["My Activity", "Your own issue/return history.", "Librarian only"],
        ["Librarians", "Create and manage librarian accounts.", "Administrator only"],
        ["Settings", "Circulation rules, email/OTP, security policy.", "Administrator only"],
    ],
)
h("3.3 Global search (header)", 2)
bullets([
    "Type a full ISBN (10 or 13 digits) and press Enter → opens Book Catalog focused on that book.",
    "Type all digits (a phone/contact number) → opens Issued/Returned Books filtered by that contact.",
    "Type any other text (title, author, student name...) → searches books first, then transactions; "
    "a toast tells you where the results are shown.",
])
h("3.4 Notifications", 2)
bullets([
    "The bell icon shows an unread badge. Click it to open the list (latest 50).",
    "Per-item: ✓ marks one as read, ✕ dismisses it. \"Mark all read\" clears the badge. \"Refresh\" reloads.",
    "Empty state: \"You're all caught up. No notifications.\"",
])

# ---------------- 4. Dashboard ----------------
h("4. Dashboard", 1)
bullets([
    "KPI cards: Total Books, Available Copies, Issued Books, Overdue.",
    "\"Issued vs Returned\" line chart — the last 30 days of activity.",
    "\"Books by Category\" pie chart — click it to enlarge; click outside to close.",
    "\"Overdue Books\" panel — each entry shows book, student and days overdue; click an entry to jump to "
    "Issued/Returned Books filtered to Overdue.",
])

# ---------------- 5. Book Catalog ----------------
h("5. Book Catalog", 1)
p("The central register of every book in the library.")
h("5.1 Finding books", 2)
bullets([
    "Search box: matches title, author or ISBN as you type.",
    "Category dropdown: filter by one category.",
    "Status chips: All | Available | Unavailable. \"Clear All\" removes every filter.",
    "Results are paginated; use the pager at the bottom.",
])
h("5.2 Adding a book", 2)
steps([
    "Click \"Add Book\".",
    "ISBN: type a 10- or 13-digit ISBN. In Add mode the app looks the ISBN up online (Open Library / Google Books) "
    "and auto-fills Title, Author and Category when found — check them before saving. Dashes and spaces are allowed; "
    "they are cleaned automatically.",
    "Title and Author are required. (On import, a blank author becomes \"Anonymous\"; when adding manually you must type one.)",
    "Pick a Category from the dropdown, or click \"+ New category…\" / the \"Create '<name>'\" chip to create one on the spot.",
    "Copies: how many physical copies you own (minimum 1).",
    "Shelf Location: e.g. A-12 (optional).",
    "Click Save. Toast: \"Book '<title>' added successfully.\"",
])
h("5.3 Editing a book", 2)
bullets([
    "Row action Edit. The ISBN is locked — \"ISBN is the book's identity and cannot be changed.\"",
    "Copies cannot be reduced below the number of copies currently issued.",
    "Title, Author, Category, Copies and Shelf Location can be changed; Save confirms with a toast.",
])
h("5.4 Viewing and QR codes", 2)
bullets([
    "View (eye icon): read-only dialog with all book details.",
    "QR (icon): generates a PNG QR code of the book's details (title, author, ISBN, shelf) — print and paste it on the book.",
])
h("5.5 Deleting a book", 2)
bullets([
    "Row action Delete → confirmation dialog \"Delete '<title>'\".",
    "A book with active (un-returned) loans cannot be deleted: \"This book has active transactions and cannot be deleted.\"",
    "A book with past history is hidden (deactivated) instead of erasing its history.",
])

# ---------------- 6. Import Books ----------------
h("6. Importing Books from a File", 1)
p("Import lets you add many books at once from a spreadsheet or CSV instead of typing each one. "
  "Nothing is saved until you confirm in the preview — the preview shows exactly what will happen row by row.")
h("6.1 Supported file formats", 2)
bullets([
    ".csv, .xlsx, .xls and .json are accepted. Any other extension shows \"Unsupported file format: <ext>\".",
    "CSV: encoding is auto-detected; the delimiter can be comma, semicolon, tab or pipe.",
    "Reading .xls (the old Excel format) requires the xlrd package; prefer .xlsx or .csv if possible.",
])
h("6.2 Columns your file should have", 2)
table(
    ["Column", "Required", "Notes / accepted variations"],
    [
        ["Title", "Yes", "Header aliases: Book Title, Name, Book Name…"],
        ["Author", "No", "Blank becomes \"Anonymous\". Aliases: Writer, Written By…"],
        ["ISBN", "Yes", "10 or 13 digits; dashes/spaces stripped; Excel scientific notation (e.g. 9.78043902348E+12) is fixed automatically. Aliases: ISBN-13, ISBN No…"],
        ["Category", "No", "New categories are created automatically during import. Aliases: Genre, Subject, Type…"],
        ["Total Copies", "No", "Defaults to 1. Aliases: Quantity, Qty, Stock, Count…"],
        ["Shelf Location", "No", "Aliases: Shelf, Rack, Location, Almirah, Section…"],
    ],
)
p("Tips: a header row is recommended but not mandatory (headerless files are detected automatically). "
  "Example header: Title, Author, ISBN, Category, Total Copies, Shelf Location.")
h("6.3 How to import", 2)
steps([
    "Book Catalog → \"Import Books\" → pick your file.",
    "The \"Import Preview\" dialog loads: \"N ready, N merged, N errors\".",
    "Use the filter chips All | Ready | Merged | Errors to review each group.",
    "Check the Status column: green \"Ready\", amber \"Merged\", red badge = the exact error for that row.",
    "Click \"Import\" (disabled when there are 0 ready and 0 merged rows), then \"Close\".",
    "Final toast: \"Import complete: N new books added, N catalog books gained copies, N errors.\" "
    "(plus \"N new categories created.\" when applicable).",
])
h("6.4 Import preview — statuses", 2)
table(
    ["Status", "Meaning", "What happens when you click Import"],
    [
        ["Ready (green)", "New, valid book.", "A new book is added to the catalog."],
        ["Merged (amber)", "The ISBN already exists in the catalog, or repeats an earlier row in this file. "
                          "Message e.g. \"Exists in catalog — 5 copies across 2 rows will be added.\" or \"Merged into row 1 (+2 copies).\"", "Copies are ADDED to the existing book (not duplicated)."],
        ["Error (red)", "The row cannot be imported.", "The row is skipped; fix the file and re-import it."],
    ],
)
p("Preview note: the table truncates long titles/authors for display only — the full values are imported.")
h("6.5 Import errors and how to fix them", 2)
p("Each red row shows one of the messages below. Fix these rows in your spreadsheet/CSV, save the file, "
  "and import it again — only the corrected rows need re-importing.", italic=True)
table(
    ["Error message in Preview", "What it means", "How to fix the file manually"],
    [
        ["Title is required.",
         "The Title cell of that row is empty/blank.",
         "Open the file, find the row (the # column shows its order), and type the book's title in the Title column. Save and re-import."],
        ["ISBN is required.",
         "The row has no ISBN value (and nothing ISBN-like to fall back on).",
         "Add the 10- or 13-digit ISBN for that book in the ISBN column."],
        ["Invalid ISBN format.",
         "The ISBN digits don't add up — its check digit is wrong (typo), or characters remain that couldn't be cleaned.",
         "Re-type the ISBN carefully from the book's back cover, or verify the check digit (use any online ISBN checker). Dashes and spaces are fine; stray letters are not."],
        ["Conflicts with row N: title, author differ.",
         "Two rows in the same file share one ISBN but describe different books (listed fields differ).",
         "Either make both rows identical on the listed fields (they are copies of the same book), or give the second book its own ISBN so it becomes a separate entry."],
        ["Differs from cataloged book: title.",
         "The ISBN already exists in the catalog, but this row's title/author/category/shelf differs from the stored record.",
         "Correct the row so it matches the cataloged book, or leave the Shelf cell EMPTY (an empty shelf defers to the catalog entry). If the catalog entry itself is wrong, edit the book in Book Catalog instead of importing."],
        ["Category 'xyz' not found and no Uncategorized fallback.",
         "The category couldn't be matched or created (rare).",
         "Use a category name that already exists (close matches attach automatically) or any new simple name — new categories are created automatically. Avoid odd characters in the category cell."],
        ["Unsupported file format: <ext>",
         "The file isn't .csv/.xlsx/.xls/.json.",
         "Re-save the file as CSV (UTF-8) or Excel .xlsx, then import again."],
        ["Could not read file: <error>",
         "The file is corrupted, password-protected, or locked by another program.",
         "Close the file in Excel (a lock file can block reading), re-save it, and try again."],
    ],
)
p("Not errors — expected messages you can safely ignore:")
bullets([
    "\"Exists in catalog — N copies across M rows will be added.\" — copies of an already-cataloged book will be added.",
    "\"Merged into row N (+k copies).\" — a repeated ISBN inside the same file; copies are folded together.",
    "If everything merges and nothing is Ready, the Import button still works — it just adds copies to existing books.",
])

# ---------------- 7. Categories ----------------
h("7. Categories", 1)
bullets([
    "\"Add Category\" → Category Name (required, e.g. Fiction) + optional Description → Save. "
    "Errors: \"Category name is required.\", \"A category with this name already exists.\"",
    "Columns show Name, Description and how many Books use the category.",
    "Edit via the row action; Delete asks for confirmation and refuses if the category still has books: "
    "\"This category has books assigned and cannot be deleted.\" — reassign those books first.",
    "Limits: name ≤ 100 characters, description ≤ 500 characters.",
])

# ---------------- 8. Issued/Returned Books ----------------
h("8. Issued/Returned Books (Student Loans)", 1)
h("8.1 Issuing a book", 2)
steps([
    "Click \"Issue Book\".",
    "Search for the book (title or ISBN) and select it in the Book dropdown — the option shows "
    "\"Title — Author (N available)\". Only books with an available copy appear.",
    "Fill Student Name, Contact Number (10-digit mobile), Class (1–12).",
    "For classes 11–12 a Stream is required: Science, Commerce or Humanities. Section (e.g. A) is optional.",
    "Click Issue. Toast: \"'<title>' issued to <student>.\" The Due Date is today plus the Loan Period "
    "(Settings, default 14 days).",
])
p("Common errors: \"This book has no available copies.\" (all copies out), "
  "\"This contact number already has an active loan for this book.\" (the same student already borrowed it — "
  "return it first), \"Enter a valid phone number.\"")
h("8.2 Returning a book", 2)
steps([
    "Find the loan (chips Issued / Overdue help) and click its Return action.",
    "Confirm in the \"Return Book\" dialog.",
    "If the book is late and fines are enabled, the fine is calculated automatically: "
    "days late × Fine Rate per day. Toast: \"'<title>' returned with a fine of ₹N.NN.\"",
])
h("8.3 Filters, search and receipts", 2)
bullets([
    "Search by book title, or by student name/contact in the second search box.",
    "Date range: From/To Date + \"Apply Dates\".",
    "Status chips: All | Issued | Overdue | Returned.",
    "View receipt: per-row dialog with Transaction #, Book, Student, Contact, Class, Issued/Due/Returned dates, Status and Fine.",
])

# ---------------- 9. Teachers ----------------
h("9. Teachers (Loans and Registry)", 1)
h("9.1 Issuing to a teacher", 2)
steps([
    "Teachers module → \"Issue Book\".",
    "Pick the book (same rules as student loans), then pick the Teacher from the dropdown (\"Name — Contact\").",
    "Click Issue. Teachers have NO fines — returns are always free.",
])
p("Errors: \"No active teachers in the registry — add one first.\", \"This teacher is deactivated.\", "
  "\"This teacher already has an active loan for this book.\"")
h("9.2 Managing the Teacher Registry", 2)
steps([
    "Click \"Manage Teachers\" (top of the Teachers screen) → the Teacher Registry opens; "
    "\"Back to Issues\" returns.",
    "\"Add Teacher\": Full Name + Contact Number (10-digit, must be unique) + optional Subject (e.g. Physics).",
    "Search by name, contact or subject; Activate/Deactivate teachers with the row actions "
    "(deactivated teachers cannot borrow).",
])

# ---------------- 10. Reports ----------------
h("10. Reports", 1)
steps([
    "Choose Report Type: DAILY, WEEKLY, MONTHLY, YEARLY or CUSTOM (From/To dates appear only for CUSTOM).",
    "Optionally filter by Academic Year (e.g. 2026 - 2027), Category and Librarian.",
    "Click \"Run Report\". KPIs appear: Issued, Returned, Overdue, Fines Collected, plus a table "
    "(by day / week / month / year depending on type).",
    "Export with \"Export PDF\" or \"Export Excel\" — choose the destination in the save dialog; "
    "toast confirms \"Report saved to <path>\".",
])
p("Custom range errors: \"Select From and To dates for a custom report.\" and \"Start Date must not be later than End Date.\"")

# ---------------- 11. My Activity ----------------
h("11. My Activity (Librarians)", 1)
p("A read-only history of everything YOU have issued and returned — useful for checking your own shift's work. "
  "Filters: status chips, From/To Date + Apply Dates. Columns: Book, Student, Class, Issued, Due, Returned, Status, Fine. "
  "Only librarians see this module; administrators do not.")

# ---------------- 12. Librarians ----------------
h("12. Librarians (Administrator Only)", 1)
steps([
    "Librarians → \"Add Librarian\": Full Name, Email Address, Temporary Password "
    "(minimum 8 characters — give it to the librarian out-of-band).",
    "The list shows Name, Email, Added On and Status (Active/Inactive).",
    "Reset a password: row action 🔑 → \"Reset Password — <name>\" → type a New Temporary Password → Save. "
    "Toast: \"Temporary password set for <name>.\"",
    "Deactivate/Activate: a deactivated librarian cannot sign in at all.",
])
p("Errors: \"An account with this email already exists.\", password-policy messages (see 2.2), "
  "\"Full name is required.\", \"Enter a valid email address.\"")

# ---------------- 13. Settings ----------------
h("13. Settings (Administrator Only)", 1)
p("Settings controls how the library behaves. It has three cards, each with its own Save button — "
  "changes apply immediately after saving. (Librarians do not see this module.)")
h("13.1 Circulation Rules", 2)
table(
    ["Field", "Default", "What it does", "Validation"],
    [
        ["Loan Period (days)", "14",
         "How many days a book may be borrowed. Due Date on every new issue = today + this value.",
         "\"Enter a positive number of days.\" / \"Loan Period must be a positive integer.\""],
        ["Fine Rate (₹/day)", "5",
         "Amount charged per late day when fines are enabled. Applied at return: days late × rate.",
         "\"Enter a positive fine rate.\" / \"Fine Rate must be positive when fines are enabled.\""],
        ["Charge Late Fines (toggle)", "Off",
         "Master switch for fines. Off = no fine is ever calculated. Teacher loans are never fined.",
         "—"],
    ],
)
p("Save shows the toast \"Circulation rules saved.\"")
h("13.2 Email & OTP", 2)
table(
    ["Field", "What it does", "Validation / notes"],
    [
        ["Gmail Account", "The Gmail address used to send OTP/reset emails (e.g. you@gmail.com).",
         "\"Enter a valid email address.\" Saved to the local .env file only — never to the database."],
        ["App Password", "The Google App Password for that account (NOT your normal Gmail password — "
                         "create one at myaccount.google.com → App passwords).",
         "\"App Password is required.\" The field is cleared after saving and is never shown again."],
        ["OTP Expiry Window (minutes)", "How long a password-reset code stays valid (default 10).",
         "\"Enter a positive number of minutes.\""],
    ],
)
p("Below the card: \"Send Test Email\" — sends a test message (subject \"LMS test email\") to the configured account. "
  "Success: \"Test email sent. Check the inbox of the configured account.\" "
  "Failures: \"Email delivery is not configured. Contact your administrator.\" or "
  "\"Could not confirm SMTP delivery. Please check the configuration and try again.\" "
  "Always click this button after changing the account or password.")
h("13.3 Security Policy", 2)
table(
    ["Field", "Default", "What it does", "Validation"],
    [
        ["Minimum Password Length", "8",
         "The minimum length for every account password (registration, librarian creation, password resets).",
         "\"Minimum password length must be at least 8.\""],
    ],
)
p("Save shows the toast \"Security policy saved.\" Passwords must also contain at least one uppercase letter, "
  "one lowercase letter and one digit (the symbol shown in some dialogs is not actually required).")
h("13.4 After changing settings", 2)
bullets([
    "Circulation Rules affect the NEXT issues/returns (already-issued books keep their original due dates).",
    "Email changes affect OTP/reset emails immediately — verify with \"Send Test Email\".",
    "Minimum Password Length affects new passwords only; existing passwords keep working until changed.",
])

# ---------------- 14. Troubleshooting ----------------
h("14. Troubleshooting", 1)
table(
    ["Symptom", "Cause", "Solution"],
    [
        ["\"Could not connect to the database.\"", "MySQL (XAMPP) is not running.",
         "Start MySQL via the XAMPP Control Panel, then restart the app."],
        ["\"Too many failed login attempts.\"", "5 wrong passwords within 15 minutes (default).",
         "Wait out the timer, or restart the app to clear the lock."],
        ["No OTP email arrives.", "SMTP not configured, or wrong Gmail/APP password.",
         "Administrator: Settings → Email & OTP → set Gmail Account + App Password → \"Send Test Email\". "
         "Note: the app shows the same message for unknown emails (security)."],
        ["Login refused after an import/manual edit of users.", "Password doesn't meet policy.",
         "Use Forgot Password to set a compliant password (8+ chars, upper, lower, digit)."],
        ["Import button stays disabled.", "0 ready and 0 merged rows — every row has an error.",
         "Open the Errors filter, read each message, fix those rows in the file (see 6.5), re-import."],
        [".xls import fails about 'xlrd'.", "The xlrd package isn't installed.",
         "Re-save the file as .xlsx or .csv, or install xlrd (pip install 'xlrd>=1.2,<2.0')."],
        ["\"MySQL shutdown unexpectedly\" in XAMPP after closing the app.",
         "Cosmetic: XAMPP Control Panel notices MySQL stopping. MySQL itself shuts down cleanly.",
         "Safe to ignore — data files are not affected. Or don't start MySQL before launching the app."],
        ["ISBN lookup doesn't auto-fill.", "No internet, or the ISBN isn't in the online databases.",
         "Type the details manually — lookup is optional."],
    ],
)

h("Appendix A — Quick reference", 1)
table(
    ["Task", "Where"],
    [
        ["Add one book", "Book Catalog → Add Book"],
        ["Add many books at once", "Book Catalog → Import Books (see chapter 6)"],
        ["Create a category", "Categories → Add Category (or inline while adding a book/importing)"],
        ["Issue/return a student loan", "Issued/Returned Books → Issue Book / row Return"],
        ["Issue/return a teacher loan", "Teachers → Issue Book / row Return"],
        ["Add a teacher", "Teachers → Manage Teachers → Add Teacher"],
        ["Create a librarian", "Librarians → Add Librarian (admin)"],
        ["Change loan period / fine", "Settings → Circulation Rules (admin)"],
        ["Configure OTP emails", "Settings → Email & OTP + Send Test Email (admin)"],
        ["Circulation/fine report", "Reports → Run Report → Export PDF/Excel"],
        ["My own history", "My Activity (librarian)"],
    ],
)

doc.save(OUT)
print(f"OK: {OUT}")
