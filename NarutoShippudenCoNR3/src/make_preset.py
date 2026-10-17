#!/usr/bin/env python3
"""Generate the Naruto Shippuden: Clash of Ninja Revolution III (RNEEDA) full-screen preset for Dolphin.

The game supports 16:9 natively (Wii widescreen setting, Dolphin's default). Dolphin's Widescreen
Hack plus Aspect Ratio "Stretch to Window" already fit its 3D to any screen shape, but every 2D
element (HUD, menus, text) gets stretched with the picture.

This preset adds one Dolphin patch ([OnFrame], re-applied every frame, so it holds after loading
any save state). It hooks the SDK's C_MTXOrtho (0x8030D078), which every 2D path in the game uses
to build its orthographic projection, and widens the requested 2D space to the screen's shape:

  * narrower than 16:9 (foldables, 4:3, 16:10): taller by (16/9)/aspect (Vert+), so the UI keeps
    its shape with extra room above and below.
  * wider than 16:9 (21:9, 32:9): wider by aspect/(16/9) (Hor+), extra room at the sides.

Which 2D spaces:
  * 16:9-shaped ones (|r-l|/|b-t| 1.70-1.86): menus and text (854x480) and the 3D-HUD camera
    (+-416 x +-230.9). Widened around their center (the UI sits in a centered 16:9 band).
  * The battle HUD layout (640x480, built in 0x80191608; the C_MTXOrtho call returns to
    0x80191764). Vert+ keeps its top edge, so the health bars stay at the top of the screen.
  * Every other 4:3-shaped space (full-screen fades and effect layers) is left stock, so they
    still cover the whole picture; widening those leaves seams.

A 4:3-shaped space is matched by its caller: the return address of the C_MTXOrtho call, or of
the call to the game's ortho wrapper 0x80016C78 (read from the wrapper's stack frame).

Patch code lives in free low memory at 0x80002B00 (0x80001800 is avoided: with cheats off, Dolphin
HLE-hooks it as the homebrew-reload stub and executing it ends emulation).

Usage (give the screen once; portrait numbers are flipped to landscape):
  python3 make_preset.py                               # default: OPPO Find N6 inner screen, 2480x2248
  python3 make_preset.py --width 2400 --height 1080    # exact resolution
  python3 make_preset.py --aspect 21:9                 # ratio as W:H, WxH or a decimal
  python3 make_preset.py --from-adb                    # read the connected phone's current screen
  python3 make_preset.py --out RNEEDA.ini
"""
import argparse
import re
import struct
import subprocess
import sys

GAME_ID = "RNEEDA"            # Naruto Shippuden: Clash of Ninja Revolution III, USA
STOCK_ASPECT = 16 / 9

ORTHO_HOOK = 0x8030D078       # C_MTXOrtho(mtx r3, t f1, b f2, l f3, r f4, n f5, f f6)
ORTHO_ORIG = 0xED641828       # fsubs f11,f4,f3 (first instruction)
ORTHO_BACK = 0x8030D07C
CAVE = 0x80002B00
# A 2D space counts as 16:9 when |r-l|/|b-t| is within this range: menus/text use 854x480
# (1.779), the battle HUD camera (0x801793D4) uses +-416 x +-230.886 (1.8017).
RATIO_LO, RATIO_HI = 1.70, 1.86
# 4:3-shaped (640x480) 2D spaces are widened only for these callers; the others are full-screen
# effect layers that must keep covering the whole picture.
RATIO43_LO, RATIO43_HI = 1.30, 1.37
ORTHO_WRAPPER_RET = 0x80016CCC  # return address of C_MTXOrtho inside the 0x80016C78 wrapper
HUD_CALLERS = [0x80191764]   # battle HUD layout (0x80191608, called once per frame from 0x80125478)

VIDEO = {
    "InternalResolution": "2",   # the owner's setting on the OPPO Find N6 (Adreno 840)
    "AspectRatio": "3",          # Stretch to Window
    "wideScreenHack": "True",    # fits the 3D to the screen; the patch fixes the 2D
}


def parse_aspect(text: str):
    """'16:10', '2480x2248', '21/9' or '1.1032' -> (label, aspect>=1). Portrait is flipped."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:xX/]\s*(\d+(?:\.\d+)?)\s*", text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a <= 0 or b <= 0:
            sys.exit(f"bad aspect: {text}")
        w, h = max(a, b), min(a, b)
        label = f"{w:g}x{h:g}" if "x" in text.lower() else f"{w:g}:{h:g}"
        return label, w / h
    try:
        v = float(text)
    except ValueError:
        sys.exit(f"bad aspect '{text}' - use W:H (16:10), WxH (2480x2248) or a decimal (1.6)")
    if v <= 0:
        sys.exit(f"bad aspect: {text}")
    v = max(v, 1 / v)
    return f"{v:.4f}:1", v


def screen_from_adb(serial=None):
    """Current screen of the connected Android device, landscape (foldables: the active screen)."""
    cmd = ["adb"] + (["-s", serial] if serial else []) + ["shell", "wm", "size"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"adb failed ({e}) - connect the phone first (adb devices)")
    sizes = re.findall(r"(Physical|Override) size: (\d+)x(\d+)", out)
    if not sizes:
        sys.exit(f"couldn't read screen size from: {out.strip()}")
    kind, a, b = sizes[-1]
    w, h = max(int(a), int(b)), min(int(a), int(b))
    print(f"adb: {kind.lower()} size {a}x{b} -> landscape {w}x{h}", file=sys.stderr)
    return w, h


def f32_bits(v: float) -> int:
    return struct.unpack(">I", struct.pack(">f", v))[0]


def b(frm: int, to: int) -> int:
    return 0x48000000 | ((to - frm) & 0x03FFFFFC)


def lis_ori(reg: int, value: int):
    return [0x3C000000 | reg << 21 | (value >> 16), 0x60000000 | reg << 21 | reg << 16 | (value & 0xFFFF)]


def lfs(frd: int, off: int, ra: int) -> int:
    return 0xC0000000 | frd << 21 | ra << 16 | (off & 0xFFFF)


def a_form(xo: int, d: int, a: int, b_: int = 0, c: int = 0, op: int = 59) -> int:
    return op << 26 | d << 21 | a << 16 | b_ << 11 | c << 6 | xo << 1


def fsubs(d, a, b_): return a_form(20, d, a, b_)
def fadds(d, a, b_): return a_form(21, d, a, b_)
def fdivs(d, a, b_): return a_form(18, d, a, b_)
def fmuls(d, a, c): return a_form(25, d, a, 0, c)
def fabs_(d, b_): return 63 << 26 | d << 21 | b_ << 11 | 264 << 1
def fcmpo(a, b_): return 63 << 26 | a << 16 | b_ << 11 | 32 << 1          # cr0


def assemble(base: int, items):
    """items: words, ("label", name) or (branch_opcode, name) for b/bc with a 16/26-bit offset."""
    labels, pc = {}, base
    for it in items:
        if isinstance(it, tuple) and it[0] == "label":
            labels[it[1]] = pc
        else:
            pc += 4
    out, pc = [], base
    for it in items:
        if isinstance(it, tuple):
            if it[0] == "label":
                continue
            op, name = it
            disp = labels[name] - pc
            out.append(op | (disp & (0x03FFFFFC if op == 0x48000000 else 0xFFFC)))
        else:
            out.append(it)
        pc += 4
    return out, labels


BLT, BGT, BNE, BEQ, B = 0x41800000, 0x41810000, 0x40820000, 0x41820000, 0x48000000


def ortho_patch(aspect: float, callers_43=HUD_CALLERS):
    """Hook C_MTXOrtho: widen 16:9-shaped 2D spaces always, 4:3-shaped ones only for the listed
    callers (return address of the C_MTXOrtho call, or of the call to the 0x80016C78 wrapper)."""
    vert = aspect < STOCK_ASPECT
    k = STOCK_ASPECT / aspect if vert else aspect / STOCK_ASPECT
    lo, hi = (1, 2) if vert else (3, 4)          # widen t/b (f1/f2) or l/r (f3/f4)
    D = {"r169_lo": 0x0, "r169_hi": 0x4, "r43_lo": 0x8, "r43_hi": 0xC, "half": 0x10, "halfk": 0x14, "k": 0x18,
         "list": 0x1C}
    items = [0x3D800000, 0x618C0000,                       # lis/ori r12, data (patched below)
             fsubs(7, 4, 3), fsubs(8, 2, 1), fdivs(9, 7, 8), fabs_(9, 9),   # f9 = |w/h|
             lfs(10, D["r169_lo"], 12), fcmpo(9, 10), (BLT, "is43"),
             lfs(10, D["r169_hi"], 12), fcmpo(9, 10), (BGT, "is43"),
             (B, "apply"),
             ("label", "is43"),
             lfs(10, D["r43_lo"], 12), fcmpo(9, 10), (BLT, "done"),
             lfs(10, D["r43_hi"], 12), fcmpo(9, 10), (BGT, "done"),
             0x7D6802A6,                                   # mflr r11 (C_MTXOrtho is a leaf)
             *lis_ori(10, ORTHO_WRAPPER_RET), 0x7C0B5000,  # cmpw r11,r10
             (BNE, "lookup"),
             0x81610044,                                   # lwz r11,0x44(r1) (wrapper's caller)
             ("label", "lookup"),
             0x394C0000 | (D["list"] - 4),                 # addi r10,r12,list-4
             ("label", "next"),
             0x852A0004, 0x2C090000, (BEQ, "done"),        # lwzu r9,4(r10) ; cmpwi r9,0 ; beq
             0x7C095800, (BNE, "next"),                    # cmpw r9,r11 ; bne
             *([(B, "apply_top")] if vert else []),        # listed HUD layouts stay at the top
             ("label", "apply"),
             fadds(7, lo, hi), fsubs(8, hi, lo),           # f7 = lo+hi ; f8 = hi-lo
             lfs(12, D["half"], 12), lfs(10, D["halfk"], 12),
             fmuls(7, 7, 12), fmuls(8, 8, 10),             # center ; half extent * k
             fsubs(lo, 7, 8), fadds(hi, 7, 8),
             *([(B, "done"),
                ("label", "apply_top"),                    # keep t (screen top), grow downward
                fsubs(8, 2, 1), lfs(10, D["k"], 12), fmuls(8, 8, 10), fadds(2, 1, 8)] if vert else []),
             ("label", "done"),
             ORTHO_ORIG, ("back", None)]
    n = sum(1 for it in items if not (isinstance(it, tuple) and it[0] == "label"))
    back_pc = CAVE + 4 * (n - 1)
    items[-1] = b(back_pc, ORTHO_BACK)
    code, _ = assemble(CAVE, items)
    data_addr = CAVE + 4 * len(code)
    code[0:2] = lis_ori(12, data_addr)
    data = [f32_bits(v) for v in (RATIO_LO, RATIO_HI, RATIO43_LO, RATIO43_HI, 0.5, 0.5 * k, k)]
    data += list(callers_43) + [0]
    entries = [(CAVE + 4 * i, w) for i, w in enumerate(code + data)]
    entries.append((ORTHO_HOOK, b(ORTHO_HOOK, CAVE)))
    mode = "Vert+" if vert else "Hor+"
    return f"{mode} 2D/UI (2D height x {k:.4f})" if vert else f"{mode} 2D/UI (2D width x {k:.4f})", entries


def render(aspect: float, label: str, callers_43=None) -> str:
    if abs(aspect - STOCK_ASPECT) < 1e-3:
        sys.exit("Screen is 16:9 - the game already fits it; no preset needed.")
    mode = "Vert+" if aspect < STOCK_ASPECT else "Hor+"
    name, entries = ortho_patch(aspect, HUD_CALLERS if callers_43 is None else callers_43)
    out = [
        f"# Naruto Shippuden: Clash of Ninja Revolution III [{GAME_ID}] - full-screen preset for {label} ({aspect:.4f}:1, {mode})",
        "# Generated by NarutoShippudenCoNR3/src/make_preset.py (github.com/kirankunigiri/ultrawide-game-patches)",
        "[Video_Settings]",
        *[f"{k} = {v}" for k, v in VIDEO.items()],
        "[OnFrame]",
        f"${name} for {label}",
        *[f"0x{a:08X}:dword:0x{w:08X}" for a, w in entries],
        "[OnFrame_Enabled]",
        f"${name} for {label}",
        "",
    ]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--aspect", help="screen ratio: W:H (16:10), WxH (2480x2248) or decimal (1.6)")
    src.add_argument("--from-adb", action="store_true", help="read the connected phone's screen via 'adb shell wm size'")
    ap.add_argument("--width", type=int, help="screen width in pixels (with --height)")
    ap.add_argument("--height", type=int, help="screen height in pixels (with --width)")
    ap.add_argument("--serial", help="adb serial for --from-adb (default: the only device)")
    ap.add_argument("--hud-callers", help=argparse.SUPPRESS)   # development: comma-separated hex list
    ap.add_argument("--out", help="file to write (default: print to stdout)")
    a = ap.parse_args()

    if (a.width is None) != (a.height is None):
        ap.error("--width and --height go together")
    if a.width is not None and (a.aspect or a.from_adb):
        ap.error("give the screen once: --width/--height, --aspect or --from-adb")
    if a.aspect:
        label, aspect = parse_aspect(a.aspect)
    else:
        if a.from_adb:
            w, h = screen_from_adb(a.serial)
        elif a.width is not None:
            w, h = max(a.width, a.height), min(a.width, a.height)
        else:
            w, h = 2480, 2248
        label, aspect = f"{w}x{h}", w / h

    hud = [int(x, 16) for x in a.hud_callers.split(",")] if a.hud_callers else None
    text = render(aspect, label, hud)
    if not a.out:
        print(text, end="")
        return
    with open(a.out, "w", newline="\n") as f:
        f.write(text)
    print(f"wrote {a.out}  ({label}, {aspect:.4f}:1, {'Vert+' if aspect < STOCK_ASPECT else 'Hor+'})")


if __name__ == "__main__":
    main()
