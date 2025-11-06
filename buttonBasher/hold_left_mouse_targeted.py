# hold_left_mouse_targeted.py
# Windows-only, no third-party deps (ctypes + stdlib)
# Usage examples:
#   python hold_left_mouse_targeted.py                -> global hold (like your original)
#   python hold_left_mouse_targeted.py --window "Minecraft"  -> try targeted hold to that window
#   python hold_left_mouse_targeted.py --window "Notepad" --x 100 --y 80

import time
import ctypes
import argparse
import msvcrt
from ctypes import wintypes

# ---------------------------
# Win32 constants & prototypes
# ---------------------------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# SendInput stuff (global mode)
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx",          wintypes.LONG),
        ("dy",          wintypes.LONG),
        ("mouseData",   wintypes.DWORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    )

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    )

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg",    wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )

class _INPUTunion(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )

class INPUT(ctypes.Structure):
    _fields_ = (
        ("type",   wintypes.DWORD),
        ("union",  _INPUTunion),
    )

SendInput = user32.SendInput

def mouse_event(flags):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
    n = SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    if n != 1:
        raise ctypes.WinError(ctypes.get_last_error())

def mouse_down_global():
    mouse_event(MOUSEEVENTF_LEFTDOWN)

def mouse_up_global():
    mouse_event(MOUSEEVENTF_LEFTUP)

# Window messages (targeted mode)
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP   = 0x0202
WM_MOUSEMOVE   = 0x0200
MK_LBUTTON     = 0x0001

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

def pack_lparam_xy(x, y):
    # low word = x, high word = y
    return (y << 16) | (x & 0xFFFF)

def get_client_size(hwnd):
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return width, height

def find_window_by_title_substring(substring):
    substring = substring.lower()

    found = []

    def _enum_proc(hwnd, lparam):
        # skip invisible windows
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if substring in title.lower():
            found.append((hwnd, title))
        return True

    user32.EnumWindows(EnumWindowsProc(_enum_proc), 0)
    # prefer the last active (front-most) by z-order (rough heuristic)
    return found[0] if found else (None, None)

def send_mouse_hold_to_window(hwnd, x=None, y=None):
    # Choose a point: center of client area if not provided
    w, h = get_client_size(hwnd)
    if x is None or y is None:
        x = w // 2
        y = h // 2

    lparam = pack_lparam_xy(x, y)

    # Nudge mouse position message first (some apps want a move at coords)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    # Press & hold
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)

def release_mouse_hold_from_window(hwnd, x=None, y=None):
    w, h = get_client_size(hwnd)
    if x is None or y is None:
        x = w // 2
        y = h // 2

    lparam = pack_lparam_xy(x, y)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)

def main():
    parser = argparse.ArgumentParser(description="Hold left mouse globally or for a specific window (no focus steal). Press 'q' to release.")
    parser.add_argument("--window", "-w", type=str, help="Substring of the window title to target (e.g., 'Minecraft' or 'Notepad'). If omitted, uses global SendInput.")
    parser.add_argument("--x", type=int, default=None, help="Client X coordinate (pixels) inside the target window (optional).")
    parser.add_argument("--y", type=int, default=None, help="Client Y coordinate (pixels) inside the target window (optional).")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds to wait before starting (switch to the app, etc.).")
    args = parser.parse_args()

    print(f"Starting in {args.delay} seconds...")
    time.sleep(args.delay)

    targeted = args.window is not None

    if targeted:
        hwnd, title = find_window_by_title_substring(args.window)
        if not hwnd:
            print(f"Could not find a visible window containing: {args.window!r}")
            print("Tip: Make sure the window is open (borderless/windowed works best), and try a different substring.")
            return
        print(f"Targeting window: {title} (HWND={hwnd})")
        print("Holding LEFT mouse (background). Press 'q' to release.")
        try:
            send_mouse_hold_to_window(hwnd, args.x, args.y)
            while True:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch.lower() == 'q':
                        break
                time.sleep(0.05)
        finally:
            release_mouse_hold_from_window(hwnd, args.x, args.y)
            print("Released. Goodbye!")
    else:
        print("Global mode: Holding LEFT mouse. Press 'q' to release.")
        try:
            mouse_down_global()
            while True:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch.lower() == 'q':
                        break
                time.sleep(0.05)
        finally:
            mouse_up_global()
            print("Released. Goodbye!")

if __name__ == "__main__":
    main()
