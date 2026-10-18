#!/usr/bin/env python3
"""Generate the Smash Ultimate aspect-ratio camera patch (Eden / yuzu-family pchtxt).

The patch rewrites 7 instructions in the game's perspective-projection builder so the
3D camera matches any screen shape while the game's own camera logic stays 16:9:

  * screen narrower than 16:9 (foldables, 4:3, 16:10): Vert+ - keep the stock 16:9
    horizontal field of view and show extra view above/below.
  * screen wider than 16:9 (21:9, 32:9): Hor+ - keep the stock vertical field of view
    and show extra view left/right.

It also adds a UI patch (unless --no-ui): the game's 2D UI (menus, text, fight HUD) is
squeezed to its correct 16:9 shape in a band across the screen (Vert+: a horizontal band in
the middle; Hor+: a vertical band) and clipped to the stock 16:9 frame, so UI the game parks
just off-screen stays hidden.

Use it with Eden's per-game aspect ratio set to "Stretch to window". Only Smash Ultimate
13.0.2 (main build ID CBD5A9B5...) is supported; see ../notes.md for how the offsets were
found and how to port them to another version.

Usage (pick ONE way to give the screen shape; landscape, i.e. width >= height):
  python3 make_vertplus.py                              # default: OPPO Find N6 inner screen, 2480x2248
  python3 make_vertplus.py --width 5120 --height 1440   # exact resolution
  python3 make_vertplus.py --aspect 16:10               # ratio as W:H, WxH or a decimal (1.6)
  python3 make_vertplus.py --from-adb                   # read the connected phone's current screen
  python3 make_vertplus.py --aspect 21:9 --out ../dist  # write <name>/exefs/13.0.2.pchtxt
"""
import argparse
import os
import re
import struct
import subprocess
import sys

NSOBID_13_0_2 = "CBD5A9B56EA859BA11CA069B19B666101AE56F5A"
STOCK_ASPECT = 16 / 9

# Perspective path of the camera builder (13.0.2 memory addresses = pchtxt offsets with
# offset_shift 0x100). Original code, for reference:
#   03555564 movi v7.2d,#0 | 03555568 mov v4.16b,v7.16b | 0355556C mov v16.16b,v7.16b
#   03555570 fdiv s2,s3,s2 (P00=f/aspect) | 03555574 mov v16.s[1],v3.s[0] (P11=f)
#   03555578 fmul s3,s0,s1 | 0355557C mov v4.s[0],v2.s[0]
BASE = 0x03555564

# UI: nn::ui2d::DrawInfo::SetProjectionMtx (0x44D60, 17 words + 3 padding) is the one place
# every UI projection is stored; both pictures (via the 0x44EA0 copy) and text (TextBox ->
# 0x79150) read it from DrawInfo+0x10. Its callers: the game's UI renderer (0x3775070) and
# nn::ui2d::Capture (0x43400, render-to-texture, left stock).
UI_BASE = 0x00044D60
UI_LIMIT = 0x00044DB0
UI_CAPTURE = 0x00043400     # nn::ui2d::Capture virtual (callers at 0x434D8 / 0x43540)


def fmov_imm8_value(imm8: int) -> float:
    """Decode an A64 FMOV (scalar, immediate) imm8 to its single-precision value."""
    sign = (imm8 >> 7) & 1
    b = (imm8 >> 6) & 1
    cd = (imm8 >> 4) & 3
    efgh = imm8 & 0xF
    exp = ((b ^ 1) << 7) | ((0b11111 if b else 0) << 2) | cd
    bits = (sign << 31) | (exp << 23) | (efgh << 19)
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def nearest_fmov(target: float):
    best = min(range(256), key=lambda i: abs(fmov_imm8_value(i) - target))
    return best, fmov_imm8_value(best)


def enc_fmov_imm(rd: int, imm8: int) -> int:     # fmov sRd, #imm
    return 0x1E201000 | (imm8 << 13) | rd


def enc_fmul(rd: int, rn: int, rm: int) -> int:  # fmul sRd, sRn, sRm
    return 0x1E200800 | (rm << 16) | (rn << 5) | rd


def ui_words(aspect: float):
    """Replacement SetProjectionMtx: copy the 4x4 (row-major, row 3 = w), then
      z = (stock row + w) / 2  -> clip-space z leaves 0..w outside the stock 16:9 frame
                                  (the game uses 0..1 depth), so off-frame UI is clipped
      row 1 (Vert+) or row 0 (Hor+) *= k  -> UI keeps its 16:9 shape in a band
    Calls from nn::ui2d::Capture are copied unchanged."""
    vert_plus = aspect < STOCK_ASPECT
    k = aspect / STOCK_ASPECT if vert_plus else STOCK_ASPECT / aspect
    row = 1 if vert_plus else 0
    b = UI_BASE
    adr_capture = UI_CAPTURE - (b + 8)
    code = [
        0xAD400420,                                   # ldp q0, q1, [x1]
        0xAD410C22,                                   # ldp q2, q3, [x1, #0x20]
        0x10000000 | ((adr_capture & 3) << 29) | (((adr_capture >> 2) & 0x7FFFF) << 5) | 9,  # adr x9, Capture
        0xCB0903C9,                                   # sub x9, x30, x9
        0xF108013F,                                   # cmp x9, #0x200
        0x54000000 | (((0x18 >> 2) & 0x7FFFF) << 5) | 3,   # b.lo store (+0x18)
        0x4E23D402 | (row << 5),                      # fadd v2.4s, vR.4s, v3.4s
        0x4F03F406,                                   # fmov v6.4s, #0.5
        0x6E26DC42,                                   # fmul v2.4s, v2.4s, v6.4s
        0x1C000000 | (((0x14 >> 2) & 0x7FFFF) << 5) | 4,   # ldr s4, k (+0x14)
        0x4F849000 | (row << 5) | row,                # fmul vR.4s, vR.4s, v4.s[0]
        0xAD008400,                                   # store: stp q0, q1, [x0, #0x10]
        0xAD018C02,                                   # stp q2, q3, [x0, #0x30]
        0xD65F03C0,                                   # ret
        struct.unpack("<I", struct.pack("<f", k))[0], # k
    ]
    assert b + 4 * len(code) <= UI_LIMIT
    return k, code


def parse_aspect(text: str):
    """'16:10', '2480x2248', '21/9' or '1.1032' -> (label, aspect>=1). Portrait is flipped."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:xX/]\s*(\d+(?:\.\d+)?)\s*", text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a <= 0 or b <= 0:
            sys.exit(f"bad aspect: {text}")
        w, h = max(a, b), min(a, b)
        label = f"{w:g}x{h:g}" if "x" in text.lower() else f"{w:g}-{h:g}"
        return label, w / h
    try:
        v = float(text)
    except ValueError:
        sys.exit(f"bad aspect '{text}' - use W:H (16:10), WxH (2480x2248) or a decimal (1.6)")
    if v <= 0:
        sys.exit(f"bad aspect: {text}")
    v = max(v, 1 / v)
    return f"{v:.4f}", v


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
    kind, a, b = sizes[-1]  # an Override size (if set) is what apps actually get
    w, h = max(int(a), int(b)), min(int(a), int(b))
    print(f"adb: {kind.lower()} size {a}x{b} -> landscape {w}x{h}", file=sys.stderr)
    return w, h


def build(width: float, height: float = 1.0):
    aspect = width / height
    if abs(aspect - STOCK_ASPECT) < 1e-4:
        sys.exit("Screen is already 16:9 - no patch needed.")
    vert_plus = aspect < STOCK_ASPECT
    factor = aspect / STOCK_ASPECT if vert_plus else STOCK_ASPECT / aspect
    imm8, used = nearest_fmov(factor)
    words = [
        0x6F00E407,                 # movi v7.2d, #0
        0x1E221862,                 # fdiv s2, s3, s2        P00 = f / aspect
        enc_fmov_imm(4, imm8),      # fmov s4, #factor
        enc_fmul(3, 3, 4) if vert_plus else enc_fmul(2, 2, 4),  # P11 *= k  |  P00 *= k
        0x6E0360F0,                 # ext v16.16b, v7.16b, v3.16b, #12   -> (0, P11, 0, 0)
        0x1E210803,                 # fmul s3, s0, s1        (original)
        0x1E204044,                 # fmov s4, s2            -> (P00, 0, 0, 0)
    ]
    return aspect, vert_plus, factor, used, words


def render(width: float, height: float, label: str, ui: bool = True) -> str:
    aspect, vert_plus, factor, used, words = build(width, height)
    err = (used / factor - 1) * 100
    mode = "Vert+" if vert_plus else "Hor+"
    which = "P11 (vertical)" if vert_plus else "P00 (horizontal)"
    lines = [
        f"@nsobid-{NSOBID_13_0_2}",
        "",
        f"# Super Smash Bros. Ultimate [01006A800016E000] 13.0.2 - {mode} camera for {label} ({aspect:.4f}:1)",
        "// Generated by SmashUltimate/src/make_vertplus.py (github.com/kirankunigiri/ultrawide-game-patches)",
        "// Perspective builder @0x3555418: f = 1/tan(fov/2); P00 = f/aspect; P11 = f.",
        f"// Patch: {which} *= {used:g} (exact {factor:.4f}; nearest FMOV immediate, {err:+.2f}%).",
        "// Use Eden's per-game aspect ratio \"Stretch to window\".",
        *([f"// UI: nn::ui2d::DrawInfo::SetProjectionMtx @0x44D60 - UI {('height' if vert_plus else 'width')} x {ui_words(width / height)[0]:.4f}",
           "// (16:9 band), clipped to the stock 16:9 frame; nn::ui2d::Capture left stock."] if ui else []),
        "",
        "@flag print_values",
        "@flag offset_shift 0x100",
        "",
        "@enabled",
    ]
    for i, w in enumerate(words):
        lines.append(f"{BASE + 4 * i:08X} {struct.pack('<I', w).hex().upper()}")
    if ui:
        k, code = ui_words(width / height)
        for i, w in enumerate(code):
            lines.append(f"{UI_BASE + 4 * i:08X} {struct.pack('<I', w).hex().upper()}")
    lines += ["@stop", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--aspect", help="screen ratio: W:H (16:10), WxH (2480x2248) or decimal (1.6)")
    src.add_argument("--from-adb", action="store_true", help="read the connected phone's screen via 'adb shell wm size'")
    ap.add_argument("--width", type=int, help="screen width in pixels (with --height)")
    ap.add_argument("--height", type=int, help="screen height in pixels (with --width)")
    ap.add_argument("--serial", help="adb serial for --from-adb (default: the only device)")
    ap.add_argument("--no-ui", action="store_true", help="camera only: leave the UI stretched (no UI patch)")
    ap.add_argument("--out", default=None,
                    help="directory to write '<name>/exefs/13.0.2.pchtxt' into (default: print to stdout)")
    ap.add_argument("--name", default=None, help="mod folder name (default: VertPlus-<screen> / HorPlus-<screen>)")
    a = ap.parse_args()

    if (a.width is None) != (a.height is None):
        ap.error("--width and --height go together")
    if a.width is not None and (a.aspect or a.from_adb):
        ap.error("give the screen once: --width/--height, --aspect or --from-adb")
    if a.aspect:
        label, aspect = parse_aspect(a.aspect)
        width, height = aspect, 1.0
    else:
        if a.from_adb:
            w, h = screen_from_adb(a.serial)
        elif a.width is not None:
            w, h = max(a.width, a.height), min(a.width, a.height)
        else:
            w, h = 2480, 2248
        label, width, height = f"{w}x{h}", w, h

    text = render(width, height, label, ui=not a.no_ui)
    if not a.out:
        print(text, end="")
        return
    _, vert_plus, factor, used, _ = build(width, height)
    name = a.name or f"{'VertPlus' if vert_plus else 'HorPlus'}-{label}"
    path = os.path.join(a.out, name, "exefs", "13.0.2.pchtxt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)
    print(f"wrote {path}  (factor {factor:.4f} -> {used:g}, {(used / factor - 1) * 100:+.2f}%)")


if __name__ == "__main__":
    main()
