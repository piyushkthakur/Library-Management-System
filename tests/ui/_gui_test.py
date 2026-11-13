"""Automated LMS GUI tester: focus, click, screenshot, type."""
import time, os, sys, ctypes, json
import win32gui, win32con, pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

SCREENSHOTS = r"C:\Users\Piyush Kumar\AppData\Local\Temp\lms_live"
os.makedirs(SCREENSHOTS, exist_ok=True)

def find_flutter_window():
    results = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if title:
                results.append((hwnd, title, cls))
    win32gui.EnumWindows(cb, None)
    for h, t, c in results:
        if 'FLUTTER_RUNNER' in c:
            return h
    return None

def focus_app():
    """Minimize everything except the Flet app, then click it to foreground."""
    flet = find_flutter_window()
    if not flet:
        print("ERROR: Flet window not found")
        return False
    
    # Minimize all non-essential windows
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if hwnd != flet:
                title = win32gui.GetWindowText(hwnd)
                cls = win32gui.GetClassName(hwnd)
                if 'Progman' not in cls and 'Shell_Tray' not in cls and 'Shell_TrayWnd' not in cls:
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                    except:
                        pass
    win32gui.EnumWindows(cb, None)
    time.sleep(0.5)
    
    # Restore and click the Flet window
    win32gui.ShowWindow(flet, win32con.SW_RESTORE)
    time.sleep(0.2)
    rect = win32gui.GetWindowRect(flet)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    pyautogui.click(cx, cy)
    time.sleep(1)
    return True

def screenshot(name):
    time.sleep(0.5)
    img = pyautogui.screenshot()
    path = os.path.join(SCREENSHOTS, f"{name}.png")
    img.save(path)
    print(f"  [{name}] {os.path.getsize(path)} bytes")
    return path

def click(x, y, delay=1.0):
    pyautogui.click(x, y)
    time.sleep(delay)

def type_text(text, delay=0.05):
    pyautogui.typewrite(text, interval=delay)

def hotkey(*keys):
    pyautogui.hotkey(*keys)
    time.sleep(0.5)

# ===== MAIN TEST SEQUENCE =====
if __name__ == "__main__":
    if not focus_app():
        sys.exit(1)
    
    print("=== LOGIN SCREEN ===")
    screenshot("01_login_initial")
    
    # Test 1: Empty submit
    print("\n--- Test: Empty submit ---")
    click(860, 400)  # Sign In button area
    screenshot("02_login_empty_submit")
    
    # Test 2: Type email only
    print("\n--- Test: Email only ---")
    pyautogui.click(650, 248)  # Email field
    time.sleep(0.3)
    type_text("librarian@example.com")
    click(860, 400)
    screenshot("03_login_email_only")
    
    # Test 3: Type wrong password
    print("\n--- Test: Wrong password ---")
    pyautogui.click(650, 343)  # Password field
    time.sleep(0.3)
    type_text("wrongpassword")
    click(860, 400)
    time.sleep(2)
    screenshot("04_login_wrong_pass")
    
    # Test 4: Correct login
    print("\n--- Test: Correct login ---")
    # Clear fields first
    pyautogui.click(650, 248)
    hotkey('ctrl', 'a')
    type_text("librarian@example.com")
    pyautogui.click(650, 343)
    hotkey('ctrl', 'a')
    type_text("Test@123")
    click(860, 400)
    time.sleep(3)
    screenshot("05_after_login")
    
    print("\nDone! Check screenshots in:", SCREENSHOTS)
