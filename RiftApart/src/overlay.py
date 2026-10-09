# Transparent, click-through, always-on-top overlay window for drawing over the game.
# run(draw_fn): draw_fn(canvas, w, h) is called every interval and manages its own items
# (it decides when to clear/redraw). ROOT is exposed so callers can change opacity.
import ctypes, tkinter as tk

GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x8000000
KEY = "#010203"   # this colour is fully transparent
ROOT = None

def set_alpha(a):
    if ROOT is not None:
        ROOT.attributes("-alpha", a)

def run(draw_fn, interval_ms=50, x=0, y=0, w=None, h=None, wake=None):
    """wake: optional threading.Event; when set, draw_fn runs within ~5 ms instead of
    waiting for the next interval (draw_fn is expected to clear it)."""
    global ROOT
    prev_fg = ctypes.windll.user32.GetForegroundWindow()   # give focus back after creating the window
    root = ROOT = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", KEY)
    w = w or root.winfo_screenwidth(); h = h or root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{x}+{y}")
    c = tk.Canvas(root, width=w, height=h, bg=KEY, highlightthickness=0)
    c.pack()
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    st = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
        st | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    if prev_fg:
        ctypes.windll.user32.SetForegroundWindow(prev_fg)

    def tick():
        try:
            draw_fn(c, w, h)
        except Exception as e:
            c.delete("all")
            c.create_text(20, 20, anchor="nw", fill="red", text=f"overlay error: {e}")
        root.after(interval_ms, tick)

    def fast():
        if wake.is_set():
            try:
                draw_fn(c, w, h)
            except Exception as e:
                c.delete("all")
                c.create_text(20, 20, anchor="nw", fill="red", text=f"overlay error: {e}")
        root.after(5, fast)
    tick()
    if wake is not None:
        fast()
    root.mainloop()

if __name__ == "__main__":
    def test(c, w, h):
        c.delete("all")
        c.create_rectangle(w - 260, 40, w - 40, 260, outline="#00e0ff", width=3)
        c.create_text(w - 150, 150, text="overlay test", fill="#00e0ff", font=("Segoe UI", 14))
    run(test)
