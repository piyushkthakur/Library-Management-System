"""Launcher for the LMS Flet app.

Sets SSL certs before flet CLI touches the network, then either:
  - `python run.py`          → runs the app directly via ft.run()
  - `python run.py app/main.py` → invokes `flet` CLI with SSL fix injected
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    # In the bundle, assets and migrations live under _internal (= _MEIPASS).
    ROOT = sys._MEIPASS
os.chdir(ROOT)

try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

if len(sys.argv) > 1:
    sys.exit(subprocess.call([sys.executable, "-m", "flet", *sys.argv[1:]]))

sys.path.insert(0, ROOT)

import flet as ft

from app.core.config import load_environment
from app.main import main

load_environment()

try:
    from app.core.logging_config import setup_logging
    setup_logging()
except Exception:
    pass  # diagnostics must never prevent the app from starting

if FROZEN:
    # flet can't infer a script dir from a function target — pass bundled assets.
    ft.run(main, assets_dir=os.path.join(ROOT, "assets"))
else:
    ft.run(main)
