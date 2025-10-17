# hold_left_mouse.py  (Windows, no third-party deps)
import time
import ctypes
from ctypes import wintypes
import msvcrt

# Win32 constants
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
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
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

SendInput = ctypes.windll.user32.SendInput

def mouse_event(flags):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
    # Send one INPUT
    n = SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    if n != 1:
        raise ctypes.WinError(ctypes.get_last_error())

def mouse_down():
    mouse_event(MOUSEEVENTF_LEFTDOWN)

def mouse_up():
    mouse_event(MOUSEEVENTF_LEFTUP)

if __name__ == "__main__":
    print("Starting in 5 seconds... switch to your target window.")
    time.sleep(5)
    print("Holding LEFT mouse button. Press 'q' to release.")
    try:
        mouse_down()
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch.lower() == 'q':
                    break
            time.sleep(0.05)
    finally:
        mouse_up()
        print("Released. Goodbye!")
