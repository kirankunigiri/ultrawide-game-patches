# Making a Wii game fill any screen in Dolphin (Vert+/Hor+ patches)

A step-by-step method for making a Wii game render full-screen with correct proportions on any
screen shape in Dolphin - a nearly square foldable, a 20:9 phone, a 21:9 or 32:9 monitor -
including its UI. It was worked out on Super Mario Galaxy 2 (see
[../SuperMarioGalaxy2/notes.md](../SuperMarioGalaxy2/notes.md) for that game's details and
addresses); everything here is meant to transfer to other games.

The end product is a per-game Dolphin settings file (`GameSettings/<GAMEID>.ini`) with a few
`[OnFrame]` patches, generated per screen shape by a small script.

## 0. Tools

| Tool | Use |
|---|---|
| Dolphin (a recent dev build on Android Adreno 8xx; see the SMG2 notes) | Running and testing |
| [nodtool](https://github.com/encounter/nod) | `nodtool extract -p data game.rvz out/` -> `out/sys/main.dol` (RVZ/ISO/WBFS) |
| Python 3 + [capstone](https://www.capstone-engine.org/) 5 | Disassembly: `CS_ARCH_PPC`, `CS_MODE_32 \| CS_MODE_BIG_ENDIAN \| CS_MODE_PS` (paired singles) |
| [SuperMarioGalaxy2/src/tools/dol.py](../SuperMarioGalaxy2/src/tools/dol.py) | DOL loader, `dis2` (disassemble around an address), `func_bounds`, `find_str`, `xrefs` (lis/addi string references) |
| adb | Copying the game image and settings to/from a phone |

Use your own copy of the game.

## 1. Get a clean, fast baseline first

Fix performance and rendering bugs before touching the aspect ratio, or you will chase the wrong
problem. Measure in real gameplay, from a save state, on the real display (a background or
virtual display can be throttled). Typical Android findings: Vulkan vs OpenGL can differ in
correctness, Hybrid Ubershaders avoid stutter, "compile shaders before starting" can cost a minute
per boot, and some enhancements (graphics mods, XFB to RAM) are expensive or buggy per game.

## 2. Quick check with Dolphin's Widescreen Hack

Settings: **Aspect Ratio = Stretch to Window** + **Widescreen Hack on**. Dolphin then scales the
vertical (narrow screen) or horizontal (wide screen) terms of **every** perspective projection
to the window shape (`Present.cpp`, `fAspectRatioHack*`).

- If the 3D looks right, Vert+/Hor+ suits the game and the rest of this guide is about doing it
  precisely.
- Note what breaks: scenes that draw 2D-looking things with a perspective camera (storybook
  pages, title cards, mini-maps) usually do. The UI (orthographic) is untouched by the hack, so it
  comes out stretched.

## 3. Look for existing aspect codes

Search for the exact game ID (e.g. `SB4E01`) plus "16:9", "21:9", "widescreen", "aspect" on
code sites (GameHacking.org, WiiRD forum archives, personal code pages such as gamemasterplc's,
the Dolphin wiki and forums). Even undocumented codes are maps:

- A float written as **(4/3)/aspect** or **(16/9)/aspect** is almost always a UI/layout scale.
- A replaced width/height call (`li rX, <number>` over a `bl`) in a function that then calls
  `tanf` is the camera projection builder.
- A `C2` code loading a float constant in a tiny getter is usually a FOV or culling value.
- `60000000` (nop) over a branch after a call is often an "is widescreen" check.

## 4. Find the projection

From `main.dol`:

1. **`tanf`** callers: projection builders compute `cot = 1/tan(fov/2)`. Look for
   `fov * 2pi/720` or `fov * 0.5` then `bl tanf`, then `fdivs fX, 1.0, f(tan)`.
2. **`C_MTXPerspective`** (Revolution SDK): `fovY f1, aspect f2, near f3, far f4`, writes
   `m[0][0] = cot/aspect`, `m[1][1] = cot` (offsets 0x00 and 0x14). Many games build the matrix
   inline instead.
3. **`GXSetProjection(mtx, type)`**: find it by its many callers passing `li r4,0`
   (perspective) or `li r4,1` (orthographic). Following a perspective caller's matrix pointer
   back tells you where the camera stores its projection.
4. Identify the **gameplay camera**: usually a singleton/scene object; note how code reaches it
   (`lwz` chains off r13) so a hook can test for it.

Map the matrix: row-major 4x4 floats; vertical terms `m[1][1]` (0x14) and `m[1][2]` (0x18),
horizontal terms `m[0][0]` (0x00) and `m[0][2]` (0x08).

## 5. The math

With **Stretch to Window**, the game's 16:9 frame is stretched to the screen of aspect A.

- **Vert+ (A < 16/9):** keep the horizontal terms; multiply the vertical terms by A/(16/9).
  Same left-right view as stock, more view above and below.
- **Hor+ (A > 16/9):** keep the vertical terms; multiply the horizontal terms by (16/9)/A.

If the game's own aspect isn't exactly 16/9 (it often comes from `width()/height()`), use the
game's value instead of 16/9 for an exact result.

## 6. Where to hook the camera

| Hook point | Pros | Cons |
|---|---|---|
| The projection builder (after `cot` is computed) | Game logic (pointer, culling, on-screen checks) sees the same matrix as the GPU | Affects everything that uses the camera, including special passes |
| The "send projection to GX" call for the gameplay camera, scaling a **copy** | Game logic stays stock; easy to exclude individual passes by caller | Game-side screen math uses the stock matrix (check the pointer) |

For SMG2 the second one won: one draw pass (the storybook page, drawn through the gameplay
camera at a fixed FOV) had to be excluded, and the stock CPU-side matrix caused no visible
problems.

**Excluding a pass by caller:** inside the hooked function the caller's return address is in
the saved-LR slot (`0x14(r1)` after a `stwu r1,-0x10(r1)` prologue). Compare it and skip:

```
lwz   r11, 0x14(r1)
lis   r12, RET@h ; ori r12, r12, RET@l
cmpw  r11, r12
beq   passthrough
```

To find which caller breaks something, bisect the caller list (skip half, test, repeat) from
one save state taken just before the broken scene.

## 7. The UI

Find where the game applies its widescreen UI adjustment: code that checks a widescreen flag
(`SCGetAspectRatio`, or a game wrapper around it) and then loads a scale such as 0.75 (or
0.7488) for x and 1.0 for y into the 2D layout system.

- **Vert+:** keep x stock and scale **y** by A/(16/9). The UI keeps its shape in a centered 16:9
  band and nothing is clipped. (Scaling x up instead keeps the shape but narrows the layout's
  visible width, so anything placed across the 16:9 width falls off the sides.)
- **Hor+:** scale x by (16/9)/A (the usual 21:9 code approach).
- Don't overwrite a shared constant (a global 1.0 used everywhere); hook the one store instead.
- Scales are often applied when a layout is **created**, so test UI changes on newly opened
  screens.
- **Alternative: hook `C_MTXOrtho`** (first instruction `fsubs f11,f4,f3`) when the game's 2D
  goes through the SDK ortho builder. Widen spaces by shape (16:9-shaped ones around their center,
  HUD layouts from their screen edge) and leave full-screen layers (often 640x480) alone. Worked
  for Naruto Shippuden: Clash of Ninja Revolution III, see
  [../NarutoShippudenCoNR3/notes.md](../NarutoShippudenCoNR3/notes.md).

## 8. Writing it as Dolphin patches

Use `[OnFrame]` patches, not Gecko codes, while developing:

- Gecko codes live in emulated memory (code handler at `0x80001800`, its code list, and every `C2`
  branch already written into game code), and save states restore all of it. A state brings
  back the codes from when it was made; removing a code from the INI doesn't remove its hooks.
- Patches are written by Dolphin every frame from the current INI, so they hold over any state.

Format (`GameSettings/<GAMEID>.ini`):

```
[OnFrame]
$My camera patch
0x80002C00:dword:0x38630074
0x8001CCAC:dword:0x4BFE5F54
[OnFrame_Enabled]
$My camera patch
```

A hook is a `b cave` written over one instruction; the cave runs the replaced instruction, the
new code, and branches back. Rules learned the hard way:

- **Code cave:** low MEM1 between `0x80001800` and `0x80003000` is free in most games, but
  **avoid `0x80001800` itself**: with cheats off Dolphin HLE-patches it as the homebrew-reload stub
  and executing it ends emulation. `0x80002000`-`0x80002FFF` worked for SMG2.
- Keep data (scratch buffers, constants) in the cave region too, and make sure code doesn't grow
  into it.
- Only use volatile registers (r0, r9-r12, f0-f13, cr0, ctr) that are dead at the hook point;
  read the surrounding code.
- `b` encoding: `0x48000000 | ((target - pc) & 0x03FFFFFC)`; conditional `beq`: `0x41820000 |
  disp`. Disassemble every patch word with capstone before testing.
- If an older version of a fix was Gecko-based, also patch the original instruction back at its
  old hook points so old save states don't keep running it.

## 9. Testing loop

1. One save state just before each scene type you care about (gameplay, menus, cutscenes,
   storybook/title cards, minigames).
2. Change the INI, restart the game, load the state, look. With patches, every test reuses the
   same state.
3. Check: 3D proportions, UI shape and clipping, cutscene text and prompts, pointer accuracy near
   the screen edges, pop-in at the extended edges.

## 10. Packaging

Write a small generator that takes the screen shape (`--width/--height`, `--aspect`, or
`--from-adb`), computes the factors, assembles the patch words, and writes the full per-game INI
with the tested settings. See [SuperMarioGalaxy2/src/make_preset.py](../SuperMarioGalaxy2/src/make_preset.py).
