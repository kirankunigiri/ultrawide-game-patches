#!/usr/bin/env python3
"""Generate the Smash Ultimate aspect-ratio camera patch (Eden / yuzu-family pchtxt).

The patch rewrites 7 instructions in the game's perspective-projection builder so the
3D camera matches any screen shape while the game's own camera logic stays 16:9:

  * screen narrower than 16:9 (foldables, 4:3, 16:10): Vert+ - keep the stock 16:9
    horizontal field of view and show extra view above/below.
  * screen wider than 16:9 (21:9, 32:9): Hor+ - keep the stock vertical field of view
    and show extra view left/right.

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


def render(width: float, height: float, label: str) -> str:
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
        "// Use Eden's per-game aspect ratio \"Stretch to window\". UI is not adjusted (stays 16:9, stretched).",
        "",
        "@flag print_values",
        "@flag offset_shift 0x100",
        "",
        "@enabled",
    ]
    for i, w in enumerate(words):
        lines.append(f"{BASE + 4 * i:08X} {struct.pack('<I', w).hex().upper()}")
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

    text = render(width, height, label)
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
