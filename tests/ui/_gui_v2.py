"""Full GUI QA v2: fixed coordinates, proper field clearing."""
import time, os, sys, ctypes, win32gui, win32con, pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

OUT = r"C:\Users\Piyush Kumar\AppData\Local\Temp\lms_live"
os.makedirs(OUT, exist_ok=True)

def find_flutter():
    r = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            if 'FLUTTER_RUNNER' in win32gui.GetClassName(h):
                r.append(h)
    win32gui.EnumWindows(cb, None)
    return r[0] if r else None

def focus_app():
    fh = find_flutter()
    if not fh:
        print("Flet window not found!"); return False
    def minimize_others(h, _):
        if h != fh and win32gui.IsWindowVisible(h):
            c = win32gui.GetClassName(h)
            if 'Progman' not in c and 'Shell_Tray' not in c:
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
    p = os.path.join(OUT, f"{name}.png")
    pyautogui.screenshot(p)
    print(f"  {name}: {os.path.getsize(p)} bytes")

def get_rect():
    fh = find_flutter()
    return win32gui.GetWindowRect(fh) if fh else None

def click(x, y, d=1.0):
    pyautogui.click(x, y); time.sleep(d)

def triple_click(x, y):
    pyautogui.click(x, y); time.sleep(0.1)
    pyautogui.click(x, y); time.sleep(0.1)
    pyautogui.click(x, y); time.sleep(0.1)

def type_text(text):
    pyautogui.typewrite(text, interval=0.02)
    time.sleep(0.2)

def select_all_and_type(cx, cy, text):
    """Click field, select all, delete, type new text."""
    pyautogui.click(cx, cy)
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.press('backspace')
    time.sleep(0.1)
    pyautogui.typewrite(text, interval=0.02)
    time.sleep(0.3)

# === MAIN ===
print("=== LMS GUI QA v2 ===\n")

if not focus_app():
    sys.exit(1)

rect = get_rect()
if not rect:
    sys.exit(1)

W, H = rect[2]-rect[0], rect[3]-rect[1]
def rx(p): return rect[0] + int(W * p)
def ry(p): return rect[1] + int(H * p)

# Login form field positions (measured from screenshots)
EMAIL_X = rx(0.50)
EMAIL_Y = ry(0.41)
PASS_X = rx(0.50)
PASS_Y = ry(0.51)
BTN_X = rx(0.50)
BTN_Y = ry(0.57)

print(f"Window: {rect}, fields: email=({EMAIL_X},{EMAIL_Y}) pass=({PASS_X},{PASS_Y}) btn=({BTN_X},{BTN_Y})")

# 1. Initial login screen
print("\n1. Login screen initial")
shot("v2_01_login")

# 2. Empty submit
print("2. Empty submit")
click(BTN_X, BTN_Y, 1.5)
shot("v2_02_empty")

# 3. Invalid email
print("3. Invalid email")
select_all_and_type(EMAIL_X, EMAIL_Y, "not-an-email")
click(BTN_X, BTN_Y, 1.5)
shot("v2_03_bad_email")

# 4. Wrong password
print("4. Wrong password")
select_all_and_type(EMAIL_X, EMAIL_Y, "librarian@example.com")
select_all_and_type(PASS_X, PASS_Y, "wrongpassword")
click(BTN_X, BTN_Y, 2.0)
shot("v2_04_wrong_pass")

# 5. Correct login
print("5. Correct login")
select_all_and_type(EMAIL_X, EMAIL_Y, "librarian@example.com")
select_all_and_type(PASS_X, PASS_Y, "Test@123")
click(BTN_X, BTN_Y, 4.0)
shot("v2_05_dashboard")

# 6. Dashboard full
print("6. Dashboard")
time.sleep(1)
shot("v2_06_dash_full")

# 7-13. Navigate all screens via sidebar
screens = [
    (0.22, "books"),
    (0.29, "categories"),
    (0.36, "transactions"),
    (0.43, "reports"),
    (0.50, "my_activity"),
    (0.57, "settings"),
    (0.64, "librarians"),
]
for i, (yp, name) in enumerate(screens, 7):
    print(f"{i}. Navigate to {name}")
    click(rx(0.06), ry(yp), 2.0)
    shot(f"v2_{i:02d}_{name}")

# 14. Back to dashboard
print("14. Back to dashboard")
click(rx(0.06), ry(0.15), 2.0)
shot("v2_14_dashboard_back")

# 15. Min resize
print("15. Min resize 1000x640")
fh = find_flutter()
if fh:
    win32gui.SetWindowPos(fh, 0, 100, 100, 1000, 640, win32con.SWP_NOZORDER)
    time.sleep(2)
    shot("v2_15_min_resize")

# 16. Max resize
print("16. Max resize 1920x1080")
if fh:
    win32gui.SetWindowPos(fh, 0, 0, 0, 1920, 1080, win32con.SWP_NOZORDER)
    time.sleep(2)
    shot("v2_16_max_resize")

print("\n=== Done ===")
