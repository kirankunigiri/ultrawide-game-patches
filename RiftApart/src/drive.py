# Drive the game for automated tests: focus its window and hold movement keys (scancodes).
import ctypes, ctypes.wintypes as wt, time

user32 = ctypes.windll.user32
SC = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "space": 0x39}
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008

class KI(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KI), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]

def _key(scan, up):
    i = INPUT(type=1)
    i.ki = KI(0, scan, KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0), 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))

def game_hwnd():
    import pymem
    pid = pymem.Pymem("RiftApart.exe").process_id
    found = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            found.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None

def focus():
    h = game_hwnd()
    if user32.GetForegroundWindow() == h:
        return True
    user32.keybd_event(0x12, 0, 0, 0); user32.keybd_event(0x12, 0, 2, 0)   # Alt tap lifts the foreground lock
    user32.ShowWindow(h, 5)
    user32.SetForegroundWindow(h)
    time.sleep(0.4)
    return user32.GetForegroundWindow() == h

def hold(key, seconds):
    _key(SC[key], False)
    time.sleep(seconds)
    _key(SC[key], True)

if __name__ == "__main__":
    import sys
    print("focused:", focus())
    time.sleep(0.5)
    for step in sys.argv[1:]:          # e.g. w:1.5 d:1
        k, _, t = step.partition(":")
        hold(k, float(t or 1))
        time.sleep(0.4)
