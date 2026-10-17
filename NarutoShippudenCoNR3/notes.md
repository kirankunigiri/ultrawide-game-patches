# Naruto Shippuden: Clash of Ninja Revolution III - Full-Screen 2D/UI Preset Notes

How the HUD and menus of Naruto Shippuden: Clash of Ninja Revolution III were made to keep their
shape on a nearly square foldable screen in Dolphin on Android. Dolphin's Widescreen Hack already
fits the 3D; one Dolphin patch on the SDK's orthographic-matrix function fixes the 2D. The general
method for Wii games is in [../docs/wii-dolphin-fullscreen-guide.md](../docs/wii-dolphin-fullscreen-guide.md);
the camera side of it is in the Super Mario Galaxy 2 notes.

## 1. The game and setup

| | |
|---|---|
| Game | Naruto Shippuden: Clash of Ninja Revolution III, USA, game ID **RNEEDA**, revision 0 (WBFS, 3.4 GB) |
| Emulator | Dolphin **2609-83** official dev build (versionCode 43165), Android |
| Device | OPPO Find N6 (CPH2765), Snapdragon 8 Elite Gen 5 (SM8850), Adreno 840, Android 16 / ColorOS |
| Screen | Inner screen 2248x2480 portrait = **2480x2248 landscape (1.1032:1)** |
| Owner's settings before the fix | Stretch to Window, Widescreen Hack on, 2x internal resolution (3D already "perfect") |
| Tools | `main.dol` extracted from the WBFS with nodtool 2.0.0-alpha.12; disassembled with capstone 5 (PPC + paired singles) via `SuperMarioGalaxy2/src/tools/dol.py` |

## 2. The problem

With Stretch to Window the whole 16:9 picture is stretched to the 1.10:1 screen. The Widescreen
Hack corrects perspective projections (3D), but not orthographic ones, so every 2D element came
out 1.61x too tall: the battle HUD (health bars, portraits, timer) and every menu (buttons, text,
frames).

No existing widescreen/HUD code for RNEEDA was found (Dolphin forum widescreen thread, Dolphin
wiki, Dolphin's built-in GameSettings).

## 3. The fix, in the order it was found

### 3.1 The game is 16:9 aware

`SCGetAspectRatio` (0x803238A0, found through the `IPL.AR` SYSCONF item table at 0x8038CFD0, item
id 1) has one caller, the boot code at 0x80171768, which stores the result as a widescreen flag at
**0x803C1A51** (`0x803C1A30 + 0x21`). Nineteen places read it. So with Dolphin's Wii widescreen
setting on (the default), the game already lays out its 2D for 16:9; the remaining problem is
only the stretch from 16:9 to the actual screen. That is the same situation as Super Mario
Galaxy 2, and the same correction applies: scale the 2D by (16/9)/aspect.

### 3.2 Where the 2D projection comes from

Two flag readers (0x80123164, 0x801231FC) pick between two calls to a wrapper at **0x80016C78**:
`(t, b, l, r, n, f) = (0, 480, 0, 854, 0, 1)` in 16:9 mode, `(0, 480, 0, 640, 0, 1)` in 4:3, then
`GXSetProjection(mtx, ortho)` (0x802E4C10). The wrapper calls the SDK's **C_MTXOrtho** at
**0x8030D078**. Every orthographic projection in the game goes through C_MTXOrtho: nine wrapper
calls plus seven direct calls (NW4R camera orthos at 0x801E8B34/0x801E8DD4, a battle HUD layout at
0x80191760, effect passes and others).

Patching each caller would be fragile, so the patch hooks C_MTXOrtho's first instruction
(`fsubs f11,f4,f3`; at entry only f1-f6 hold arguments, so f7-f12 and r9-r12 are free) and
decides by the requested space's shape.

### 3.3 Attempts

| Attempt | Result |
|---|---|
| Widen spaces with \|r-l\|/\|b-t\| 1.76-1.80 (854x480) around their center | Menus correct, in a centered 16:9 band. **Battle HUD still stretched** |
| Ratio window 1.70-1.86: also catches the 3D-HUD camera at 0x801793D4 (+-416 x +-230.886, ratio 1.8017: 16:9 adjusted for overscan) | No visible change to the battle HUD |
| Also widen every 4:3-shaped (640x480) space | Battle HUD correct, **but** a full-screen effect layer (drawn in a 640x480 space) shrank into the band and left horizontal seams at the band edges |
| 4:3 spaces only for listed callers; bisect the callers on a test screen | 0x8017A110, 0x8001697C + 0x8018B528, 0x801E8B38 + 0x801E8DD8, 0x8003D31C and 0x801371A8 did nothing; **0x80191764** (in 0x80191608) is the battle HUD |
| Battle HUD widened around its center | Correct shape, but it sat at the top of the 16:9 band, about a fifth of the way down; the owner found it "awkward close to the center" |
| **Battle HUD widened from its top edge** (t kept, b = t + (b - t) x k) | **Owner-verified:** correct shape, at the top of the screen like before the fix |

0x80191608 builds the ortho from a +-320 x +-240 layout rectangle; it is called once, from the
battle screen (0x80125478).

### 3.4 Matching a caller

C_MTXOrtho is a leaf, so LR at its entry is the return address in the caller. For calls through
the 0x80016C78 wrapper LR is 0x80016CCC; the wrapper's own caller is then read from its stack
frame (`lwz r11,0x44(r1)`, after its `stwu r1,-0x40(r1)` and `stw r0,0x44(r1)`). The cave compares
that against a zero-terminated list.

### 3.5 The patch

```
hook  0x8030D078  b 0x80002B00             (C_MTXOrtho, replaces fsubs f11,f4,f3)
cave  0x80002B00  f9 = |(r-l)/(b-t)|
                  1.70 <= f9 <= 1.86          -> widen around center
                  1.30 <= f9 <= 1.37 and caller in list
                                              -> Vert+: keep t, b = t + (b-t)*k ; Hor+: around center
                  otherwise                   -> stock
                  fsubs f11,f4,f3 ; b 0x8030D07C
data              ratio bounds, 0.5, 0.5k, k, caller list (0x80191764, 0)
```

Vert+ widens t/b (f1/f2) by k = (16/9)/aspect; Hor+ widens l/r (f3/f4) by k = aspect/(16/9).
It's an `[OnFrame]` patch, so it holds over save states (see the SMG2 notes, 4.5, for why Gecko
codes don't). Low memory 0x80002B00-0x80002BDC is used; 0x80001800 is avoided because, with cheats
off, Dolphin HLE-hooks it as the homebrew-reload stub.

## 4. Lessons

- **Check for native 16:9 first** (`IPL.AR` -> SCGetAspectRatio -> the game's flag). If the game
  already lays out for 16:9, the UI fix is the same (16/9)/aspect scale as any 16:9 game.
- **Hook the SDK ortho builder, filter by shape.** One hook covers every 2D path; full-screen
  layers are a different shape (640x480 here) and must be left alone or they leave seams.
- **Not every 16:9 space is exactly 854x480.** The HUD camera's 1.8017 sat just outside a tight
  window; use a generous one.
- **Bisect callers with a list in the cave**, not by guessing from disassembly: six restarts found
  the HUD among ten candidates.
- **HUDs want an anchor, menus want centering.** Widening around the center is right for
  full-screen menus; a top HUD should keep its top edge.
- **Test on an agent display, not the owner's screen.** A 2480x2248 Outpost agent screen matches
  the phone's shape for screenshots; a launch script that checks the display exists first avoids
  ever starting Dolphin on the owner's screen.

## 5. Configuration

- `src/make_preset.py` - per-screen preset (`--width W --height H`, `--aspect 21:9`, `--from-adb`,
  `--out FILE`). Default 2480x2248. `--hud-callers` (hidden) overrides the 4:3 caller list for
  bisecting.
- `dist/RNEEDA.ini` - generated preset for 2480x2248.
- No debug switch: the preset writes no logs.

## 6. Install

See [dist/INSTALL.md](dist/INSTALL.md).

## 7. Not covered / untested

- Other regions (Europe, Japan): different addresses, not ported.
- **Hor+ screens** (20:9 phones, 21:9, 32:9): generated, not tested.
- Battle messages that may share the battle HUD layout (round start, KO, combo counters) were not
  seen in the test save state; they would also move up with the top-anchored HUD.
- Story mode, mini-games, character select and Wi-Fi screens were not individually checked. A 2D
  screen built in a 640x480 space other than the battle HUD stays stretched; add its caller to
  `HUD_CALLERS` (or a centered list) after bisecting.
- With the Wii widescreen setting off the game draws a 4:3 UI (640x480), which the patch leaves
  alone.

## 8. Reusable discovery method

1. Find `IPL.AR` in the DOL, its pointer table, and `SCGetAspectRatio` (`li r4,1` +
   `addi r3,r1,8` + `bl SCFindU8Item`); follow its caller to the game's widescreen flag and list
   the flag's readers.
2. In a reader, look for `C_MTXOrtho` (`fsubs f11,f4,f3` first) and its argument constants: that
   gives the game's 2D space for each mode.
3. Hook C_MTXOrtho's entry, widen by shape, and test the menus and the HUD from save states.
4. When something full-screen breaks, switch that shape to a caller list and bisect it.
5. Anchor HUD layouts to their screen edge.
