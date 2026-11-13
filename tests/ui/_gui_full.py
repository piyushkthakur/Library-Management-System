"""Full GUI QA: runs all tests in one shot, no external focus needed."""
import time, os, sys, ctypes, win32gui, win32con, pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

OUT = r"C:\Users\Piyush Kumar\AppData\Local\Temp\lms_live"
os.makedirs(OUT, exist_ok=True)

def find_flutter():
    r = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            c = win32gui.GetClassName(h)
            if 'FLUTTER_RUNNER' in c:
                r.append(h)
    win32gui.EnumWindows(cb, None)
    return r[0] if r else None

def focus_and_minimize_others():
    fh = find_flutter()
    if not fh:
        print("Flet window not found!")
        return False
    def minimize_others(h, _):
        if h != fh and win32gui.IsWindowVisible(h):
            c = win32gui.GetClassName(h)
            if 'Progman' not in c and 'Shell_Tray' not in c and 'Notify' not in c:
                try: win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
                except: pass
    win32gui.EnumWindows(minimize_others, None)
    time.sleep(0.5)
    win32gui.ShowWindow(fh, win32con.SW_RESTORE)
    time.sleep(0.2)
    rect = win32gui.GetWindowRect(fh)
    pyautogui.click((rect[0]+rect[2])//2, (rect[1]+rect[3])//2)
    time.sleep(1)
    return True

def shot(name):
    time.sleep(0.8)
    img = pyautogui.screenshot()
    p = os.path.join(OUT, f"{name}.png")
    img.save(p)
    sz = os.path.getsize(p)
    print(f"  {name}: {sz} bytes")

def get_flet_rect():
    fh = find_flutter()
    if fh:
        return win32gui.GetWindowRect(fh)
    return None

def click_in_app(x, y, delay=1.0):
    pyautogui.click(x, y)
    time.sleep(delay)

def clear_field(cx, cy):
    pyautogui.click(cx, cy)
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.press('delete')
    time.sleep(0.1)

def type_in_field(cx, cy, text):
    clear_field(cx, cy)
    pyautogui.typewrite(text, interval=0.03)
    time.sleep(0.2)

# === MAIN ===
print("=== Starting LMS GUI QA ===\n")

# Focus
if not focus_and_minimize_others():
    sys.exit(1)

rect = get_flet_rect()
if not rect:
    sys.exit(1)
print(f"App window: {rect}")
W = rect[2] - rect[0]
H = rect[3] - rect[1]
# Relative coords (window starts at rect[0], rect[1])
def rx(pct): return rect[0] + int(W * pct)
def ry(pct): return rect[1] + int(H * pct)

print("\n1. LOGIN SCREEN - Initial")
shot("s01_login")

print("\n2. LOGIN - Empty submit (click Sign In with no input)")
click_in_app(rx(0.5), ry(0.56))  # Sign In button
shot("s02_empty_submit")

print("\n3. LOGIN - Invalid email format")
type_in_field(rx(0.5), ry(0.41), "not-an-email")
click_in_app(rx(0.5), ry(0.56))  # Sign In
shot("s03_invalid_email")

print("\n4. LOGIN - Wrong password")
type_in_field(rx(0.5), ry(0.41), "librarian@example.com")
type_in_field(rx(0.5), ry(0.51), "wrongpassword")
click_in_app(rx(0.5), ry(0.56))  # Sign In
time.sleep(2)
shot("s04_wrong_password")

print("\n5. LOGIN - Correct credentials")
type_in_field(rx(0.5), ry(0.41), "librarian@example.com")
type_in_field(rx(0.5), ry(0.51), "Test@123")
click_in_app(rx(0.5), ry(0.56))  # Sign In
time.sleep(4)
shot("s05_dashboard")

print("\n6. DASHBOARD - Full view")
time.sleep(1)
shot("s06_dashboard_full")

print("\n7. NAVIGATE - Books screen")
# Click sidebar books (approx 2nd nav item)
click_in_app(rx(0.06), ry(0.22))
time.sleep(2)
shot("s07_books")

print("\n8. NAVIGATE - Categories screen")
click_in_app(rx(0.06), ry(0.29))
time.sleep(2)
shot("s08_categories")

print("\n9. NAVIGATE - Transactions screen")
click_in_app(rx(0.06), ry(0.36))
time.sleep(2)
shot("s09_transactions")

print("\n10. NAVIGATE - Reports screen")
click_in_app(rx(0.06), ry(0.43))
time.sleep(2)
shot("s10_reports")

print("\n11. NAVIGATE - My Activity screen")
click_in_app(rx(0.06), ry(0.50))
time.sleep(2)
shot("s11_my_activity")

print("\n12. NAVIGATE - Settings screen")
click_in_app(rx(0.06), ry(0.57))
time.sleep(2)
shot("s12_settings")

print("\n13. NAVIGATE - Librarians screen")
click_in_app(rx(0.06), ry(0.64))
time.sleep(2)
shot("s13_librarians")

print("\n14. NAVIGATE - Back to Dashboard")
click_in_app(rx(0.06), ry(0.15))
time.sleep(2)
shot("s14_back_dashboard")

print("\n15. WINDOW - Resize to minimum (1000x640)")
try:
    fh = find_flutter()
    if fh:
        win32gui.SetWindowPos(fh, 0, 100, 100, 1000, 640, win32con.SWP_NOZORDER)
        time.sleep(2)
        shot("s15_min_resize")
except Exception as e:
    print(f"  Resize error: {e}")

print("\n16. WINDOW - Restore to max")
try:
    fh = find_flutter()
    if fh:
        win32gui.SetWindowPos(fh, 0, 0, 0, 1920, 1080, win32con.SWP_NOZORDER)
        time.sleep(2)
        shot("s16_max_resize")
except Exception as e:
    print(f"  Resize error: {e}")

print("\n=== GUI QA Complete ===")
print(f"Screenshots saved in: {OUT}")
