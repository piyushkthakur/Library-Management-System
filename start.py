"""SSL-safe launcher for Library Management System.

Sets SSL_CERT_FILE before flet starts, then launches the desktop app.
If the desktop run fails on the current system, falls back to web mode.
Use this instead of 'flet app/main.py' on systems with SSL issues.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# Set SSL certs before flet touches the network
try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
    print(f"SSL_CERT_FILE={certifi.where()}")
except ImportError:
    print("WARNING: certifi not installed. Run: pip install certifi")
    print("Trying system cert bundle...")
    try:
        import ssl
        cafile = ssl.get_default_verify_paths().cafile
        if cafile:
            os.environ["SSL_CERT_FILE"] = cafile
            print(f"SSL_CERT_FILE={cafile}")
        else:
            print("ERROR: No SSL certificates found. HTTPS connections will fail.")
    except Exception:
        print("ERROR: Could not locate SSL certificates.")

from flet.cli import main


def _run_flet(args: list) -> int:
    sys.argv = [sys.argv[0], *args]
    try:
        main()
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    except Exception as e:
        print(f"Launch failed: {e}")
        return 1
    return 0


extra = sys.argv[1:]
code = _run_flet(["run", "app/main.py", *extra])
if code != 0 and "--web" not in extra:
    print("Desktop launch failed, falling back to web mode...")
    code = _run_flet(["run", "--web", "app/main.py", *extra])
sys.exit(code)
