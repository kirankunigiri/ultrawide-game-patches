#!/usr/bin/env python3
"""Generate the Super Mario Galaxy 2 (SB4E01) full-screen preset for Dolphin.

Writes a per-game settings file (GameSettings/SB4E01.ini) that makes the game fill any
screen shape with correct proportions. It sets Aspect Ratio "Stretch to Window", turns
Dolphin's Widescreen Hack OFF, and adds two Dolphin patches ([OnFrame], re-applied by Dolphin
every frame, so they also hold after loading any save state):

  * Camera: hooks the game's "apply gameplay camera projection" routine (0x8001CC90). Right
    before GXSetProjection it copies the gameplay camera's 4x4 projection and scales it:
    narrower than 16:9 (foldables, 4:3, 16:10) scales the vertical terms (Vert+: stock left-right
    view, extra view above/below); wider than 16:9 (21:9, 32:9, 20:9 phones) scales the
    horizontal terms (Hor+). The camera object itself stays stock, so all game logic (camera,
    pointer, culling) behaves as on a TV. The one draw pass that renders the framed storybook
    page and its narration text (0x804524C0, bucket 0x26 at a fixed 15 deg FOV) is left stock;
    scaling it made the narration text and A prompt disappear.
  * UI: the game draws its 4:3-authored layouts with a per-layout (x, y) scale that the stock
    widescreen mode sets to (0.7488, 1.0). Vert+ squeezes y by aspect/(16/9) when a layout is
    created, so every layout keeps its shape inside a centered 16:9 band (nothing clipped at the
    sides). Hor+ narrows x by (16/9)/aspect (gamemasterplc's 21:9 knob).

Both values depend only on the screen shape, so the preset is generated per screen.

It also adds the Classic Controller patch from Galaxy-2-Patch by quatric (MIT, vendored in
third_party/galaxy2patch/): with Dolphin's emulated Wii Remote + Classic Controller, spin is a
button (x) instead of a shake, the left stick moves Mario, and button prompts show buttons. Its
right-stick star pointer is included as a separate patch that is off by default, so the
touchscreen (or any Wii Remote IR mapping) keeps moving the pointer. With a Nunchuk attached the
patch does nothing.
The rest of the preset is the setup tested on an OPPO Find N6 (Adreno 840): Vulkan, 2x internal
resolution, Hybrid Ubershaders, graphics mods off. See ../notes.md.

The Classic Controller code lives at 0x80001820-0x80001C6C, ours at 0x80002B00-0x80002E44 (0x80001800 is avoided: with
cheats off, Dolphin HLE-hooks it as the homebrew-reload stub and executing it ends emulation).

Usage (give the screen once; portrait numbers are flipped to landscape):
  python3 make_preset.py                               # default: OPPO Find N6 inner screen, 2480x2248
  python3 make_preset.py --width 2400 --height 1080    # exact resolution
  python3 make_preset.py --aspect 16:10                # ratio as W:H, WxH or a decimal (1.6)
  python3 make_preset.py --from-adb                    # read the connected phone's current screen
  python3 make_preset.py --aspect 21:9 --out SB4E01.ini
  python3 make_preset.py --wiimote-profile "Gamepad - Classic Controller"   # also auto-load a controller profile
  python3 make_preset.py --classic-stick-pointer       # Classic Controller: star pointer on the right stick
  python3 make_preset.py --no-classic                  # leave out the Classic Controller patch
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

GAME_ID = "SB4E01"            # Super Mario Galaxy 2, USA. Other regions have different addresses.
STOCK_ASPECT = 16 / 9
STOCK_UI_X = 0.7487684488296509   # [0x807E14F4], the stock widescreen layout x-scale

# 0x8001CC90: r3 = gameplay camera (scene object 0x18); 0x8001CCAC addi r3,r3,0x74 ;
# 0x8001CCB0 bl GXSetProjection(r3 = cam+0x74, r4 = 0 perspective).
GX_HOOK = 0x8001CCAC
GX_ORIG = 0x38630074
GX_BACK = 0x8001CCB0
GX_CAVE = 0x80002C00
GX_BUF = 0x80002E00           # 16-float matrix copy, scale factor at +0x40
# Return address (saved at 0x14(r1) by 0x8001CC90) of the storybook-page pass in 0x804524C0.
STORYBOOK_CALLER_RET = 0x80452520

OLD_GECKO_HOOK, OLD_GECKO_ORIG = 0x8011199C, 0xED6A0024   # fdivs f11,f10,f0 in builder 0x801118A0

# Layout scale setup 0x8047BB20: if widescreen, scale = ([0x807E14F4], [0x807E14E8]=1.0).
#   0x8047BB54  stfs f0, 0x14(r1)      stores the layout y-scale (from the shared 1.0 constant)
UI_Y_HOOK = 0x8047BB54
UI_Y_ORIG = 0xD0010014
UI_Y_BACK = 0x8047BB58
UI_CAVE = 0x80002B00
UI_X_ADDR = 0x807E14F4        # read only at 0x8047BB40 (layout creation)

# Galaxy-2-Patch Classic Controller data (see third_party/galaxy2patch/README.md).
CLASSIC_JSON = Path(__file__).parent / "third_party" / "galaxy2patch" / "cc_SB4E01.json"
CLASSIC_SHA256 = "60aca03bdc45a59126d69caa3f67bca3140be919658087f82af24c001471afc1"
CLASSIC_STICK_POINTER_NOTE = "Pointer right stick math hook"

# Tested setup (OPPO Find N6, Snapdragon 8 Elite Gen 5 / Adreno 840, Dolphin 2609-83).
CORE = {"GFXBackend": "Vulkan", "EnableCheats": "False"}   # no Gecko codes; patches only
VIDEO = {
    "InternalResolution": "2",             # 2x held 100% in play with this preset
    "ShaderCompilationMode": "2",          # Hybrid Ubershaders
    "WaitForShadersBeforeStarting": "False",  # the precompile took ~60 s per boot on Android Vulkan
    "AspectRatio": "3",                    # Stretch to Window
    "wideScreenHack": "False",             # replaced by the camera patch (the hack hides storybook text)
    "EnableMods": "False",                 # the Bloom Blurred mod draws a seam on this setup
    "EnableGPUTextureDecoding": "True",    # slight help at 2x on the Adreno 840, no texture issues seen
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
    kind, a, b = sizes[-1]  # an Override size (if set) is what apps actually get
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


def stfs(frs: int, off: int, ra: int) -> int:
    return 0xD0000000 | frs << 21 | ra << 16 | (off & 0xFFFF)


def camera_patch(aspect: float):
    """GX-level hook: scale a copy of the gameplay projection unless the caller is the storybook pass."""
    vert = aspect < STOCK_ASPECT
    k = aspect / STOCK_ASPECT if vert else STOCK_ASPECT / aspect
    rows = (0x14, 0x18) if vert else (0x00, 0x08)        # m[1][1], m[1][2]  |  m[0][0], m[0][2]
    code = [GX_ORIG,                                     # addi r3,r3,0x74 (original)
            0x81610014,                                  # lwz r11,0x14(r1)  (caller's return address)
            *lis_ori(12, STORYBOOK_CALLER_RET),
            0x7C0B6000,                                  # cmpw r11,r12
            "beq_end",
            *lis_ori(12, GX_BUF),
            0x3963FFFC, 0x394CFFFC,                      # addi r11,r3,-4 ; addi r10,r12,-4
            0x38000010, 0x7C0903A6,                      # li r0,16 ; mtctr r0
            0x852B0004, 0x952A0004, 0x4200FFF8,          # lwzu r9,4(r11) ; stwu r9,4(r10) ; bdnz
            lfs(1, 0x40, 12)]                            # f1 = k
    for off in rows:
        code += [lfs(0, off, 12), 0xEC000072, stfs(0, off, 12)]   # lfs f0 ; fmuls f0,f0,f1 ; stfs f0
    code += [0x7D836378]                                 # mr r3,r12
    end = 4 * len(code)
    code = [(0x41820000 | ((end - 4 * i) & 0xFFFC)) if w == "beq_end" else w for i, w in enumerate(code)]
    code.append(b(GX_CAVE + end, GX_BACK))
    assert GX_CAVE + 4 * len(code) <= GX_BUF
    entries = [(GX_CAVE + 4 * i, w) for i, w in enumerate(code)]
    entries += [(GX_BUF + 0x40, f32_bits(k)), (GX_HOOK, b(GX_HOOK, GX_CAVE))]
    # Older versions of this fix were Gecko codes that hooked the projection builder at
    # 0x8011199C; save states made with them still contain that hook. Put the original back.
    entries += [(OLD_GECKO_HOOK, OLD_GECKO_ORIG)]
    mode = "Vert+" if vert else "Hor+"
    return f"{mode} camera (projection x {k:.4f})", entries


def ui_patch(aspect: float):
    if aspect < STOCK_ASPECT:
        y = aspect / STOCK_ASPECT
        code = [*lis_ori(12, f32_bits(y)), 0x91810014]   # stw r12,0x14(r1) instead of the 1.0
        code.append(b(UI_CAVE + 4 * len(code), UI_Y_BACK))
        entries = [(UI_CAVE + 4 * i, w) for i, w in enumerate(code)] + [(UI_Y_HOOK, b(UI_Y_HOOK, UI_CAVE))]
        return f"Vert+ UI (layout y-scale {y:.4f})", entries
    x = STOCK_UI_X * STOCK_ASPECT / aspect
    return f"Hor+ UI (layout x-scale {x:.4f})", [(UI_X_ADDR, f32_bits(x)), (UI_Y_HOOK, UI_Y_ORIG)]


def classic_patches():
    """Galaxy-2-Patch Classic Controller ops as (name, entries): the patch itself, then its
    right-stick pointer hook. Without the hook the game keeps reading the Wii Remote IR pointer."""
    raw = CLASSIC_JSON.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CLASSIC_SHA256:
        sys.exit(f"{CLASSIC_JSON} doesn't match the tested version (SHA-256 differs)")
    main, stick = [], []
    for op in json.loads(raw)["ops"]:
        data = bytes.fromhex(op.get("data") or op["new"])
        assert len(data) % 4 == 0
        words = [(op["addr"] + i, int.from_bytes(data[i:i + 4], "big")) for i in range(0, len(data), 4)]
        (stick if op.get("note") == CLASSIC_STICK_POINTER_NOTE else main).extend(words)
    return [("Classic Controller (Galaxy-2-Patch by quatric)", main),
            ("Classic Controller right-stick pointer", stick)]


def render(aspect: float, label: str, show_fps: bool, profile: str | None,
           classic: bool = True, stick_pointer: bool = False) -> str:
    if abs(aspect - STOCK_ASPECT) < 1e-3:
        sys.exit("Screen is 16:9 - the game already fits it; no preset needed.")
    mode = "Vert+" if aspect < STOCK_ASPECT else "Hor+"
    patches = [(f"{name} for {label}", entries) for name, entries in (camera_patch(aspect), ui_patch(aspect))]
    enabled = [name for name, _ in patches]
    if classic:
        cc, cc_stick = classic_patches()
        patches += [cc, cc_stick]
        enabled += [cc[0]] + ([cc_stick[0]] if stick_pointer else [])
    out = [
        f"# Super Mario Galaxy 2 [{GAME_ID}] - full-screen preset for {label} ({aspect:.4f}:1, {mode})",
        "# Generated by SuperMarioGalaxy2/src/make_preset.py (github.com/kirankunigiri/ultrawide-game-patches)",
        "[Core]",
        *[f"{k} = {v}" for k, v in CORE.items()],
        "[Video_Settings]",
        *[f"{k} = {v}" for k, v in VIDEO.items()],
    ]
    if show_fps:
        out += ["ShowFPS = True", "ShowSpeed = True"]
    if profile:
        out += ["[Controls]", f"WiimoteProfile1 = {profile}"]
    out.append("[OnFrame]")
    for name, entries in patches:
        out.append(f"${name}")
        out += [f"0x{a:08X}:dword:0x{w:08X}" for a, w in entries]
    out.append("[OnFrame_Enabled]")
    out += [f"${name}" for name in enabled]
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--aspect", help="screen ratio: W:H (16:10), WxH (2480x2248) or decimal (1.6)")
    src.add_argument("--from-adb", action="store_true", help="read the connected phone's screen via 'adb shell wm size'")
    ap.add_argument("--width", type=int, help="screen width in pixels (with --height)")
    ap.add_argument("--height", type=int, help="screen height in pixels (with --width)")
    ap.add_argument("--serial", help="adb serial for --from-adb (default: the only device)")
    ap.add_argument("--show-fps", action="store_true", help="turn on Dolphin's FPS/speed counters")
    ap.add_argument("--wiimote-profile", help="controller profile to auto-load for Wii Remote 1 "
                                              "(name of a file in Config/Profiles/Wiimote/, without .ini)")
    ap.add_argument("--no-classic", action="store_true", help="leave out the Classic Controller patch")
    ap.add_argument("--classic-stick-pointer", action="store_true",
                    help="Classic Controller: move the star pointer with the right stick (off: touch/IR pointer)")
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

    if a.no_classic and a.classic_stick_pointer:
        ap.error("--classic-stick-pointer needs the Classic Controller patch")
    text = render(aspect, label, a.show_fps, a.wiimote_profile, not a.no_classic, a.classic_stick_pointer)
    if not a.out:
        print(text, end="")
        return
    with open(a.out, "w", newline="\n") as f:
        f.write(text)
    print(f"wrote {a.out}  ({label}, {aspect:.4f}:1, {'Vert+' if aspect < STOCK_ASPECT else 'Hor+'})")


if __name__ == "__main__":
    main()
