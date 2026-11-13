"""Launch the LMS Flet app, bring to foreground, screenshot all screens."""
import subprocess, time, os, sys, ctypes, ctypes.wintypes

sys.path.insert(0, r"C:\Users\Piyush Kumar\Desktop\Personal\Projects\Library Management System")

OUT = r"C:\Users\Piyush Kumar\AppData\Local\Temp\lms_live"
os.makedirs(OUT, exist_ok=True)

def find_flet_window():
    """Find the Flet app window by enumerating all windows."""
    import win32gui
    results = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if title:
                results.append((hwnd, title, cls))
    win32gui.EnumWindows(cb, None)
    return results

# Kill stale Flet
os.system('taskkill /f /im flet.exe >nul 2>&1')
time.sleep(0.5)

# Launch app via flet CLI
proc = subprocess.Popen(
    [sys.executable, '-m', 'flet.cli', 'run', 'app/main.py'],
    cwd=r"C:\Users\Piyush Kumar\Desktop\Personal\Projects\Library Management System",
)
print(f"Launched PID: {proc.pid}")
time.sleep(10)

# List all visible windows
wins = find_flet_window()
print(f"\nVisible windows ({len(wins)}):")
for h, t, c in wins:
    print(f"  hwnd={h}  class={c}  title={t[:80]}")

import pyautogui

# Try to activate a relevant window
import win32gui, win32con, win32api

flet_hwnd = None
for h, t, c in wins:
    tl = t.lower()
    if 'flet' in tl or 'library' in tl or 'lms' in tl:
        flet_hwnd = h
        break

if not flet_hwnd and wins:
    # Try any non-desktop window that's not explorer
    for h, t, c in wins:
        if c != 'Progman' and c != 'Shell_TrayWnd' and 'task' not in t.lower():
            flet_hwnd = h
            break

if flet_hwnd:
    print(f"\nActivating hwnd={flet_hwnd}")
    # Simulate Alt key release first (fixes SetForegroundWindow restrictions)
    ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt up
    time.sleep(0.1)
    win32gui.ShowWindow(flet_hwnd, win32con.SW_RESTORE)
    time.sleep(0.2)
    win32gui.SetForegroundWindow(flet_hwnd)
    time.sleep(1)
else:
    print("\nNo Flet window found!")

img = pyautogui.screenshot()
path = os.path.join(OUT, "full_desktop.png")
img.save(path)
print(f"Screenshot: {os.path.getsize(path)} bytes -> {path}")
