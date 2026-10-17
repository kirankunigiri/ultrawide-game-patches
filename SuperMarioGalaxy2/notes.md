# Super Mario Galaxy 2 - Full-Screen (Vert+/Hor+) Preset Notes

How Super Mario Galaxy 2 was made to run cleanly and fill a nearly square foldable screen in
Dolphin on Android: a tested settings preset plus two Dolphin patches, one scaling the gameplay
camera's projection on its way to the GPU and one setting the game's UI layout scale. The
general method for other Wii games is in
[../docs/wii-dolphin-fullscreen-guide.md](../docs/wii-dolphin-fullscreen-guide.md).

## 1. The game and setup

| | |
|---|---|
| Game | Super Mario Galaxy 2, USA, game ID **SB4E01** (RVZ, 1.44 GB) |
| Emulator | Dolphin **2609-83** official dev build (versionCode 43165, master `a4be0d255f`, 2026-10-16), Android |
| Device | OPPO Find N6 (CPH2765), Snapdragon 8 Elite Gen 5 (SM8850), Adreno 840, Qualcomm Vulkan driver build 05/29/26 (V@0842.44), Android 16 / ColorOS |
| Screen | Inner screen 2248x2480 portrait = **2480x2248 landscape (1.1032:1)** |
| Input | Sony DualShock 4 over Bluetooth (054c:05c4), touchscreen or phone gyroscope for the pointer |
| Tools | `main.dol` extracted from the RVZ with nodtool 2.0.0-alpha.12; disassembled with capstone 5 (PPC + paired singles); `src/tools/dol.py` |

## 2. The problems

1. **"Pretty glitchy" on Dolphin 2609a:** wrong colors and flicker. Dolphin 2609a lacks
   [PR #14899](https://github.com/dolphin-emu/dolphin/pull/14899) (merged 2026-10-04): Qualcomm
   Adreno drivers 0.700+ miscompile specialized TEV shaders when a color input A or B is Zero,
   giving wrong colors in Specialized mode and flicker in Hybrid mode.
2. **Flicker when moving, even on 2609-83:** with the OpenGL backend (Android's default),
   moving made the picture flicker with "weird frames" in every shader mode.
3. **Slow:** 40 FPS (68% speed) at 3x internal resolution.
4. **16:9 picture on a 1.10:1 screen:** thick bars, or a stretched picture with "Stretch".
5. **Pointer:** the default touch overlay covers the screen; the star pointer needs a good input.

## 3. Dolphin build and settings

| Change | Why (measured on the Find N6) |
|---|---|
| Dolphin 2609a -> **2609-83 dev build** | Includes PR #14899. `DriverDetails` gates the workaround (`BUG_BROKEN_TEV_COLOR_ZERO`) on Qualcomm drivers >= 0x802bc000 (Vulkan) / 700 (GL); this driver is 0.842 |
| Backend OpenGL -> **Vulkan** | OpenGL flickered while moving in Specialized, Hybrid and Exclusive Ubershaders, and with Fast Depth off. Vulkan: no flicker, 60 FPS |
| Internal resolution | Benchmarked in a busy scene with OpenGL: 3x 68%, 2x 82%, 1x 100%. With Vulkan and the final preset the owner found **2x** holds 100% in play, so 2x is the default |
| **Hybrid Ubershaders** | Same speed as Specialized (82% vs 82% at 2x); prevents compile stutter |
| Compile shaders before starting **off** | On Android Vulkan the precompile runs single-threaded (`BUG_BROKEN_MULTITHREADED_SHADER_PRECOMPILATION`) and took ~60 s per boot; off, boot is ~20 s and Hybrid covers new shaders |
| Graphics mods **off** | Dolphin's built-in "Bloom Blurred" mod (meant for >1x) drew a dark seam around the top-left quarter of the screen |
| Store XFB copies to texture only: **left on** | Turning it off (wiki fix for black Message Board photos) dropped speed from ~100% to ~40% |
| EFB access: left on | Dolphin's own SB4.ini enables it; the star pointer and Yoshi's tongue need it |

Performance notes: ColorOS's Games app already had Dolphin in "Pro Gamer" mode, yet the CPU
clusters were dynamically capped (1.3-2.5 GHz of 3.6/4.6 GHz). Benchmarks on an Outpost agent
(virtual) display are not representative: Dolphin runs in the `foreground` cpuset there instead
of `top-app`, with the prime cores idle.

## 4. The aspect fix, in the order it was found

### 4.1 Dolphin's Widescreen Hack (works for 3D, breaks storybook scenes)

`Present.cpp` (`UpdateDrawRectangle`) computes `adjust = source_aspect / draw_aspect`; for a window
narrower than the game it sets `fAspectRatioHackH = 1/adjust` (Vert+), and `VertexShaderManager`
multiplies the vertical rows of **every** perspective projection by it. With "Stretch to Window"
this gave a correct, full-screen 3D world immediately, and proved Vert+ suits the game. But the
framed storybook scenes lost their narration text and A prompt (and the frame was squeezed).

### 4.2 Existing codes as a map

The only published aspect codes for this game are
[gamemasterplc's](https://sites.google.com/site/gamemasterplcscheatcodes/nintendo-wii/super-mario-galaxy-2-sb4e01)
21:9 and 48:9 codes (no description). Decoded against the disassembly:

| Line | Address | What it is |
|---|---|---|
| `0447BB3C 60000000` | `0x8047BB3C` | `nop`s the "is widescreen" branch in the layout scale setup `0x8047BB20` |
| `047E14F4 3F124925` | `0x807E14F4` | layout x-scale global = (4/3)/aspect (0.5714 for 7:3; stock 0.7488) |
| `C201CE4C ...` | `0x8001CE30` | the "current camera FOV" getter (`lfs f1,0xC0(r3)`), forced to a constant |
| `0411194C 38600415` | `0x8011194C` | in the camera projection builder: replaces the screen-width call with 1045, forcing aspect = 1045/448 |
| `48 DE 58 DE 14 0000029C` | heap | same x-scale written into one early-created layout object |

### 4.3 The camera

- `0x801118A0` is the projection builder: `f19 = width()/height()`, `f11 = 1/tan(fov/2)`
  (`fov * 2pi/720`, `tanf` at `0x8063DD64`), `P00 = f11/f19`, `P11 = f11`, matrix stored at
  `cam+0x74`. It runs from the camera constructor `0x80111460` and the setters for near
  (`0x80111870`), FOV (`0x80111880`) and offset (`0x80111890`).
- Three cameras are built with it (`0x80454010`, `0x80456A60`, `0x80459A30`); the gameplay
  camera is scene object 0x18: `[[[[[r13-0x657C]+0x24]+0x12C]+0x10]+0x60]`.
- `0x8001CC90` is "apply the gameplay camera projection": `GXSetProjection(cam+0x74, perspective)`
  (`GXSetProjection` = `0x805D04B0`). It has 27 callers.

Attempts:

| # | Approach | Result |
|---|---|---|
| A | `C2` hook in the builder after `f11 = 1/tan`: `P11 *= A/aspect`, `aspect = A` | Gameplay correct; storybook text gone |
| A2 | A, applied only when the camera is scene object 0x18 | Still gone: the storybook uses the gameplay camera |
| B | Leave the camera stock; hook `0x8001CCAC` (`addi r3,r3,0x74`) to copy the matrix and scale rows P11/P12 by A/(16/9) before `GXSetProjection` | Gameplay correct; storybook text gone |
| B + skip | B, but pass the stock matrix through when the caller is one specific pass | **Final.** Found by bisecting the 27 callers (5 restarts with the same save state) |
| C | A + skip when the camera FOV is 15 (the storybook FOV) | Text back, but the storybook picture stretched |

The culprit pass is in `0x804524C0`, the per-frame draw sequence: when scene object `0x89`
(the storybook) exists it saves the FOV, sets **FOV 15.0** (`[r2+0x2590]`, used nowhere else),
calls `0x8001CC90` (return address `0x80452520`), draws bucket `0x26` (the storybook page and its
narration text), and restores the FOV. Rendering that pass with a scaled projection makes the
text and prompt vanish (most likely they are rendered into a region that is then copied as a
texture, and the scaled version falls outside it). The storybook picture itself is drawn by
other passes, which stay scaled and look correct.

Because B leaves the camera object stock, game-side math (pointer picking, on-screen checks,
culling) sees the stock 16:9 projection. In testing the star pointer still lined up with what
it pointed at across the screen, and no pop-in was reported.

### 4.4 The UI

`0x8047BB20` sets each layout's scale (stored at `layout+0x50/+0x54` by `0x8047BBA0`): widescreen
mode uses `([0x807E14F4], [0x807E14E8])` = **(0.7488, 1.0)**, 4:3 mode (1.0, 1.0).
`0x807E14F4` is read only there; `0x807E14E8` is the game's shared 1.0 constant (used
everywhere), so it is not overwritten.

| Try | Result |
|---|---|
| x = (4/3)/aspect (the 21:9 code's knob) | Correct shape, but the layout's visible width became 1.10:1: storybook text and the A prompt clipped at both sides |
| **y = A/(16/9)** via a hook on `0x8047BB54` (`stfs f0,0x14(r1)`, the y store) | **Final.** Every layout keeps its shape inside a centered 16:9 band; nothing is clipped |
| also writing y at the heap object's `+0x2A0` | Dropped: the field was never identified, and it isn't needed |

Hor+ uses the x knob (`0x807E14F4` = 0.7488 x (16/9)/A); untested.

### 4.5 Gecko codes vs. Dolphin patches (save states)

The fix started as Gecko codes. Dolphin save states contain all of MEM1, including the Gecko
code handler at `0x80001800`, its code list, and every `C2` branch already written into game
code; `GeckoCode::DoState` only restores the "installed" flag. So loading a state brought back
the code list from when it was made: changing a code meant replaying the game to test it, and
even removing all codes from the INI left the old hooks running from a state.

Dolphin **patches** (`[OnFrame]`) are written into memory by the emulator every frame from the
current INI, so they hold over any save state. The final preset uses only patches, with the
code in low memory (`0x80002B00` UI, `0x80002C00` camera, `0x80002E00` matrix scratch). Two
lessons from the switch:

- **`0x80001800` is off limits with cheats disabled:** Dolphin HLE-patches it as the
  homebrew-reload stub (`HLE.cpp`, `PatchFixedFunctions`), and executing it ends emulation. The
  first patch build put its code there and the game exited right after starting.
- **Undo old hooks explicitly:** states made with the Gecko version still contain a branch at
  `0x8011199C`; the camera patch writes the original instruction (`fdivs f11,f10,f0`) back.
- Layout scales are set at creation, so a state saved mid-scene keeps that scene's UI scale.

### 4.6 Pointer

| Attempt | Result |
|---|---|
| Right stick, IR relative | Works, "hard" to aim |
| Controller + phone gyro (`|`), IMU "Point" | Appeared on tilt then vanished: on Android Dolphin **disables "Point" (IMUIR) by default** (`IMUCursor.cpp`) |
| Phone gyro + accelerometer, Point on | Vanished at random: with the phone held upright the accelerometer told the game the remote pointed at the ceiling |
| Phone gyro into IR relative, accelerometer unmapped | Stopped vanishing; slow (relative speed capped at `STEP_PER_SEC = 2` units/s); drifted off center |
| Phone gyro into Point (absolute), no accelerometer, Total Yaw 360, FOV 30 x 22.5 | Good: same angle = same spot; R3 recenters |
| **Touch IR pointer** with the overlay shown but all buttons off | **Owner's pick.** Needs the overlay registered (`ShowInputOverlay = True`), otherwise touches never reach the IR override |

### 4.7 Classic Controller (spin on a button)

The owner wanted the touch overlay to have every action the gamepad has. With Wii Remote +
Nunchuk, spin is `Shake` (the gamepad had it on Square/R1), and Dolphin's Nunchuk overlay has no
shake button. Dolphin's overlay buttons drive fixed emulated inputs (`InputOverrider` control
IDs), so they can't be remapped to `Shake`.

Existing mod: [Galaxy-2-Patch](https://github.com/Wii-Patches/Galaxy-2-Patch) (quatric, MIT) adds
Classic Controller and GameCube controller support. The Classic Controller part:

- Allows extension type 2 in the controller manager and disables the "connect a Nunchuk" panic
  screens.
- `btn_hook` (0x804CF5D8) rebuilds the Wii Remote button word from the Classic Controller buttons.
  The game keeps a spin bit (0x0020, unused by WPAD) next to the real buttons; Classic x sets it.
- The Classic left stick is copied in as the Nunchuk stick (accelerometer zeroed).
- UI helpers swap shake prompts for button badges.
- `ptr_math_hook` (0x804CF61C) replaces the IR pointer position with an integrated right-stick
  position.

Its prebuilt data (`tools/prebuilt/cc_SB4E01.json`) lists every write with the retail bytes it
replaces, so it converts directly into `[OnFrame]` patches. Checked against our `main.dol`: every
`orig` matches, and nothing overlaps our hooks. The code blob sits at 0x80001820-0x80001C6C, below
our caves at 0x80002B00. The pinned commit is a02ef5d, newer than the v1.2 release (which has a
title-screen crash); see `src/third_party/galaxy2patch/README.md`.

- The right-stick pointer hook is split into its own patch, off by default. Without it, the
  original code copies the IR position from the KPAD sample, so Dolphin's touch IR pointer still
  works with a Classic Controller attached. The Classic overlay calls the same pointer code as the
  Wii Remote overlays.
- The GameCube controller part is not used. It lives at 0x80002400-0x80003000 (it would overlap
  our caves), and Dolphin can attach a Classic Controller directly anyway.
- Re-writing the blob every frame is free: Dolphin's patch engine only writes, and invalidates
  the JIT cache, when a value differs (`PPCDebugInterface.cpp`, `ApplyMemoryPatch`).
- Overlay layout: Dolphin's default Classic layout puts ZL/ZR and L/R at different heights and
  x/y side by side. The owner rearranged it by hand (see `dist/touch-layout.png`). Positions are in
  Dolphin's SharedPreferences in `/data/data`, which adb can't read: the app isn't debuggable, the
  phone isn't rooted, and `adb backup` skips apps targeting API 31+. So the layout is documented
  as a picture and measured centers. The toggles are in `Dolphin.ini [AndroidOverlayButtons]`.

Result: works in play on the Find N6, 60 FPS, spin on x and touch pointer.

## 5. Other settings outside the preset

- **Android 16 orientation:** `ignoreOrientationRequest` is true on the unfolded screen, so
  Dolphin's landscape lock (`[Android] EmulationOrientation`, default landscape) was ignored.
  `am compat disable UNIVERSAL_RESIZABLE_BY_DEFAULT org.dolphinemu.dolphinemu` opts Dolphin out
  (change 357141415, overridable); applying it kills the app.
- **Touch pointer overlay:** Dolphin.ini `[Android] ShowInputOverlay = True` and every
  `[AndroidOverlayButtons] ButtonToggleWiimote*/ButtonToggleNunchuk* = False`. Dolphin has no
  "hide when a gamepad is connected" option.
- **Gamepad device name:** `Android/<controller number>/<name>`; Dolphin uses Android's
  controller number as the device ID, so the first gamepad is `Android/1/...`.
- **Dolphin Android's in-game Settings menu edits the global GFX.ini**, not the game's INI.

## 6. Lessons

- **Try the emulator's own hack first, then make it precise.** The Widescreen Hack proved Vert+
  looks right; the game-side version only had to exclude what it broke.
- **Existing codes are maps.** An undocumented 21:9 code pointed at the projection builder, the
  FOV getter and the layout scale.
- **Prefer patches over Gecko codes when iterating with save states.**
- **Bisect draw passes by caller return address.** A one-line `cmpw` on the saved LR inside the
  hook, a fixed save state just before the broken scene, and halving the caller list found the
  storybook pass in 5 restarts.
- **Test in real gameplay on the real display.** Title-screen and agent-display numbers were both
  misleading.

## 7. Configuration

- `src/make_preset.py` - per-screen preset (`--width W --height H`, `--aspect 20:9`,
  `--from-adb`, `--show-fps`, `--wiimote-profile NAME`, `--classic-stick-pointer`,
  `--no-classic`, `--out FILE`). Default 2480x2248, Classic Controller patch included.
- `src/third_party/galaxy2patch/` - pinned Galaxy-2-Patch Classic Controller data + MIT license.
- `src/tools/dol.py` - DOL loader + disassembly helpers (capstone) used for the analysis.
- `dist/SB4E01.ini` - generated preset for 2480x2248.
- `dist/Profiles/Wiimote/` - `Gamepad - Classic Controller` (Wii Remote + Classic, touch
  pointer), `Gamepad - Touch Pointer`, `Gamepad - Phone Tilt Pointer`
  (FOV 30 x 22.5), `Gamepad - Right Stick Pointer` (relative, x2). Generic Wii Remote + Nunchuk
  profiles, usable in other games.
- No debug switch: the preset writes no logs.

## 8. Install

See [dist/INSTALL.md](dist/INSTALL.md).

## 9. Not covered / untested

- Other regions (SB4P01, SB4J01): different addresses, not ported.
- **Hor+ screens** (20:9 phones, the Find N6 cover screen, 21:9, 32:9): generated, not tested.
- Later storybook scenes and every galaxy were not individually checked; other special draw
  passes could need the same exclusion (bisect as in 4.3 if one breaks).
- Motion-control stages (Wii Remote tilt) are not mapped in the profiles, and weren't tried with
  the Classic Controller.
- Classic Controller: tested in early gameplay (World 1) only; the Galaxy-2-Patch GameCube
  controller part is not included.
- One Vulkan driver crash (`vulkan.adreno.so` in `QueueSubmit`) was seen around a screen
  rotation; locking orientation avoids it.
