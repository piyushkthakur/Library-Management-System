# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Library Management System — onedir, windowed.

Layout notes (consumed at runtime):
  - assets/         flet serves bg*.jpg / softwarelogo.png from
                    here (run.py passes it explicitly when frozen).
  - alembic.ini + migrations/  read by database.py for auto-migrations
                    (project_root = _internal when frozen).
  - flet_desktop/app/flet-windows.zip  offline flet desktop client;
                    flet_desktop extracts it to ~/.flet/client on first run
                    instead of downloading from GitHub.
"""
import os

from PyInstaller.utils.hooks import collect_data_files

PROJECT = os.path.abspath(os.path.join(SPECPATH, ".."))
FLET_CLIENT_ZIP = os.path.join(SPECPATH, "vendor", "flet-windows.zip")

if not os.path.isfile(FLET_CLIENT_ZIP):
    raise SystemExit(
        f"Missing {FLET_CLIENT_ZIP} — create it once with:\n"
        '  Compress-Archive -Path "%USERPROFILE%\\.flet\\client\\'
        'flet-desktop-full-0.86.4\\flet" -DestinationPath packaging\\vendor\\flet-windows.zip'
    )

datas = [
    (os.path.join(PROJECT, "app", "assets"), "assets"),
    (os.path.join(PROJECT, "alembic.ini"), "."),
    (os.path.join(PROJECT, "migrations"), "migrations"),
    (FLET_CLIENT_ZIP, "flet_desktop/app"),
    *collect_data_files("certifi"),  # cacert.pem — read by run.py / main.py
]

a = Analysis(
    [os.path.join(PROJECT, "run.py")],
    pathex=[PROJECT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # migrations/env.py is bundled as a data file, so PyInstaller cannot
        # see its `from logging.config import fileConfig` — alembic died with
        # ModuleNotFoundError in frozen builds (DB created, no tables).
        "logging.config",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Verified against sys.modules of the full app import chain: none of these
    # load at runtime — they only leak into the graph via guarded/optional
    # imports of site-packages deps (matplotlib, flet, openpyxl, ...).
    # Keep: matplotlib, dateutil (lazy dashboard charts), lxml (real chain).
    excludes=[
        "torch",
        "tensorflow",
        "scipy",
        "pandas",
        "pytest",
        "uvicorn",
        "sentry_sdk",
        "grpc",
        "django",
        "gevent",
        "onnxruntime",
        "opentelemetry",
        "fastmcp",
        "jsonschema",
        "zope",
        "gi",
        "pythoncom",
        "pywintypes",
        "win32com",
        "sklearn",
        "plotly",
        # tkinter NOT excluded: import_books_dialog.py uses it (file picker)
        "pygame",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LibraryManagementSystem",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app — no console window
    icon=os.path.join(SPECPATH, "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LibraryManagementSystem",
)
