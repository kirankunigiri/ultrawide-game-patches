# Super Smash Bros. Ultimate - Aspect Ratio Camera Patch Notes

Vert+ / Hor+ camera for Smash Ultimate under Eden, built from disassembly of the game's
projection code, plus what we learned about input latency on Android.

## 1. The game

| | |
|---|---|
| Game | Super Smash Bros. Ultimate, title ID `01006A800016E000` |
| Version | **13.0.2** - main NSO build ID `CBD5A9B56EA859BA11CA069B19B666101AE56F5A`, sdk `5FD4F531C1195E9E5510C9E73F22CD39612839F8` |
| Emulator | Eden v0.2.1 stable (Android, standard APK) |
| Tested device | OPPO Find N6 (CPH2765), Snapdragon 8 Elite Gen 5 / Adreno 840, Android 16, ColorOS. Inner screen 2248x2480 portrait = **2480x2248 landscape (1.1032:1)** |
| Firmware | 22.5.0 |

The game renders a 16:9 image. On the Find N6's nearly square inner screen that leaves
thick bars (~62% of the screen used), or a squished picture if stretched.

## 2. The problem

- Eden's aspect ratio options (16:9, 4:3, 21:9, 16:10, Stretch) only change how the 16:9
  frame is presented. **Stretch** fills the screen but distorts it (x0.62 horizontally here).
- Existing aspect mods all keep the game's **vertical** FOV ("Original Camera", Hor+). On a
  screen narrower than 16:9 that crops the sides: at 1.1032:1 you see **62% of the stock
  left-right view**, which feels zoomed in and cramped.
- What we wanted: the **stock 16:9 horizontal view, with extra view above and below**
  (Vert+), filling the whole screen with correct proportions.

## 3. The fix

### 3.1 Where the camera is built

Dump the decrypted NSO with Eden (`dump_nso=true` in `config.ini`, launch, file appears at
`files/dump/<TID>/nso/main-<buildid>.nso`; it's dumped before mods are applied). Layout is a
0x100-byte header + the decompressed memory image, so with pchtxt `@flag offset_shift 0x100`
the **pchtxt offset = memory address** (Eden's log confirms: line `03555428` is "patching
offset 0x03555528").

One function builds every camera's projection (`0x3554DE0`, `x1` = camera, `x0` = out). It
switches on `[x1,#0x150]`: 0 = perspective (`0x3555418`), 2 = scaled identity, else ortho
(`0x3555138`). The perspective path:

```
[x1,#0x160] fov   [x1,#0x154] near   [x1,#0x158] far   [x1,#0x16c] aspect (16/9)
03555420  fmul  s4, s1, s3          ; half = fov * 0.5
03555428  ldr   s2, [x1,#0x16c]     ; aspect   <- Fl4sh/AAR overwrite this with fmov #2.375
          ... polynomial sin/cos ...
03555554  fdiv  s3, s3, s4          ; tan(half)
03555560  fdiv  s3, s7, s3          ; f = 1/tan(half)
03555570  fdiv  s2, s3, s2          ; P00 = f / aspect   (horizontal)
03555574  mov   v16.s[1], v3.s[0]   ; P11 = f            (vertical)
```

### 3.2 The math

For a screen of aspect X shown with Eden "Stretch", with A0 = 16/9:

- **Vert+ (X < A0):** keep `P00 = f/A0`, set `P11 = f * X/A0`. At 1.1032 that is f x 0.6206.
- **Hor+ (X > A0):** keep `P11 = f`, set `P00 = f/A0 * A0/X`. At 32:9 that is x0.5.

The camera struct's aspect stays 16/9, so **all of the game's camera framing and zoom logic is
untouched**. Only the final projection changes. That's why it behaves exactly like the stock
camera, just with more view.

### 3.3 The patch (7 instructions, no code cave)

`.text` has no code caves (inter-function padding is at most 3 `udf #0` words), so the patch
rearranges what's there. Two vector moves are folded into single instructions:

- `mov v4,v7` + `mov v4.s[0],v2.s[0]` becomes `fmov s4, s2`. A scalar FMOV zeroes the upper lanes.
- `mov v16,v7` + `mov v16.s[1],v3.s[0]` becomes `ext v16.16b, v7.16b, v3.16b, #12`, which gives (0, x, 0, 0) because v7 = 0.

```
            original                    ->  Vert+ (2480x2248)
03555564  movi v7.2d, #0                movi v7.2d, #0
03555568  mov  v4.16b, v7.16b           fdiv s2, s3, s2      ; P00 = f/aspect (moved up)
0355556C  mov  v16.16b, v7.16b          fmov s4, #0.625
03555570  fdiv s2, s3, s2               fmul s3, s3, s4      ; Hor+: fmul s2, s2, s4
03555574  mov  v16.s[1], v3.s[0]        ext  v16.16b, v7.16b, v3.16b, #12
03555578  fmul s3, s0, s1               fmul s3, s0, s1
0355557C  mov  v4.s[0], v2.s[0]         fmov s4, s2
```

The factor must be an FMOV immediate (+-n/16 * 2^r). `make_vertplus.py` picks the nearest
one. For 0.6206 that's 0.625 (+0.7%), which you can't see. No usable literal exists within
the +-1 MB `ldr` range for an exact value.

### 3.4 Deliberately left alone

- **UI**: Eden's Stretch stretches the whole final frame, and the UI is drawn in it at 16:9.
  The patch can't fix the UI (see 4.3).
- **Culling**: the game's 16:9 frustum culling is unchanged. No pop-in was seen at the
  extended top/bottom edges in testing, but it's possible on some stages.
- Every perspective camera uses this builder, so results screens and other 3D scenes get the
  same extra view.

## 4. Everything we tried

| # | Mod | Result |
|---|---|---|
| 1 | [aar.fayaz.one](https://aar.fayaz.one/) generator (Smash = exefs) | No effect at narrow ratios. Its 13.0.2 template is Fl4sh's "21:9 **Ultrawide** Camera": `03555428 0270201E` is a hard-coded `fmov s2, #2.375` whatever ratio you enter, and your ratio only lands in the UI float at `04471C5C` (stock 16/9) |
| 2 | `[4:3 WIP] [21.9 Original Camera v13.0.4]` from [pacoa-kdbg](https://github.com/pacoa-kdbg/Switch-Emulator-Ultrawide-FPS-Mods) | Works with Eden 4:3 (~83% of screen). It's auto-converted from Fl4sh's 21:9 Original Camera, but only 14 of 31 constants were changed, so menus are partly cut off |
| 3 | Our 1.1032 conversion of #2 (+ Stretch) | Full screen, correct shape, but cramped (62% left-right view) and the UI is stretched |
| 4 | Our full conversion of Fl4sh's original (all 31 `0x4018E38E` halves -> `0x3F8D35C0`) | Looked identical to #3; the UI constant change has no visible effect |
| 5 | **This patch (Vert+)** | Final: full screen, correct shape, stock left-right view |
| 6 | UI letterbox (`src/experimental/ui-letterbox-13.0.2.pchtxt`) | Partial; see 4.3 |

Fl4sh's pack has two 21:9 families. "Ultrawide Camera" (4 lines: the aspect `fmov`, the UI
float, and two culling `fmov`s) widens the view. "Original Camera" (~31 MOVZ/MOVK pairs
loading 2.3889 in ~15 functions) keeps the zoom.

### 4.3 UI letterbox attempt (unfinished, not shipped)

The goal: keep Stretch on, but draw the UI squeezed vertically by the same factor, so menus
look like 16:9 with bars while fights stay full screen.

- `nn::ui2d` is linked with RTTI: `N2nn4ui2d8DrawInfoE` at `0x44730C0`, its typeinfo at
  `0x4F19150`, its vtable at `0x4F19128` (GOT `0x52A4580`), and the constructor at `0x44B80`.
  **DrawInfo layout:** `+0x10` projection 4x4, `+0x50` view 3x4.
- **The patch:** `0x44EA0` is the projection getter, with 2 callers (`0x53F00`, `0x665DC`)
  that copy it into the per-draw constant buffer. Scaling row 1 by 0.625 there, using 2 words
  of its `udf` padding, squeezes pictures and panes correctly: the title panel scaled x0.625
  around the frame center, which shows layouts are centered on the origin.
- **Why it isn't shipped:** **Text (nn::font) does not go through the getter**, so the HUD
  splits apart (portraits and % move up, names stay at the bottom).
- Squeezing the camera builder's ortho path (`0x3555164..88`) has no visible effect.
- The `DrawInfo` projection is set inline in app code. There are 158 stores of a 4x4 at
  `+0x10/+0x30`, and none of them is a ui2d setter.
- **Next step:** find `nn::font` RTTI and its constant-buffer setup. Even when finished, the
  HUD would sit inside the middle band.

## 5. Input latency on Android (what we learned)

Smash in Eden on the phone felt noticeably laggier than Eden on PC, with the same controller
feeling fine in native Android games.

- **Smash itself: ~6 frames (~100 ms)** on real hardware
  ([SmashWiki: Frame delay](https://www.ssbwiki.com/Frame_delay)). Native phone games are
  often 2-3 frames, which is the main reason Smash feels heavier anywhere.
- **Display path is small once fixed:** measured with
  `dumpsys SurfaceFlinger --latency`, a finished frame (GPU done) reaches the screen in a
  **median 8.9 ms (p90 11 ms)** at 120 Hz with Mailbox.
- **Biggest Android-side fixes:**
  1. **VSync Mailbox.** Eden's default FIFO lets 3+ finished frames queue (Eden requests
     minImageCount+1, at least 3, swapchain images).
  2. **120 Hz.** ColorOS "Auto select" held Eden at 90 Hz in menus and **60 Hz in-game**.
     Setting it to High allows 120 Hz. The Odin 2 Portal test measured ~46 ms at 120 Hz vs
     ~67 ms at 60 Hz on the same device
     ([r/SBCGaming](https://www.reddit.com/r/SBCGaming/comments/1gw0n7i/odin_2_portal_input_delay_testingtogether/)).
     Even on High, a fresh launch sometimes came back at 60 Hz (an app-level vote from OPPO's
     dynamic refresh; Eden's window has `dvrrWindowFrameRateHint=true`). Toggling the
     refresh setting mid-game restored 120 Hz.
  3. **Async presentation off.** It only matters if it was on.
- **Async GPU off:** removes a stage where frames can wait. The owner felt "a bit better?",
  but it was hard to tell.
- **120 FPS (Fl4sh "120FPS Proper")** halves the game's own per-frame delay. It felt better.
  Eden supports it natively: a guest swap interval <= 0 is treated as a speed multiplier
  (`hardware_composer.cpp`, `NormalizeSwapInterval`), so the mod's sdk patch (swap interval
  0) makes Eden compose at 120 Hz.
- **Not available:** Eden's "Frame pacing mode" isn't shown in the Android UI, and v0.2.1
  ignores it on Android 11+ (`vk_swapchain.cpp`). The frame-queue fix
  [PR #3730](https://git.eden-emu.dev/eden-emu/eden/pulls/3730) was never merged. No newer
  Eden build has Android latency fixes.
- **Measured elsewhere:** Switch emulation on Android is 2-6 frames slower than hardware
  ([r/SBCGaming](https://www.reddit.com/r/SBCGaming/comments/1n1u7wl/some_latency_measurements_original_hardware_vs/)).
  Expect better, not PC-equal.

`src/eden_settings.py` applies the Eden side (Mailbox, async presentation off, async shaders
on, async GPU on/off, Stretch for Smash) and optionally ColorOS refresh "High"
(`secure oplus_customize_screen_refresh_rate=3`; 0 = Auto select).

## 6. Configuration

- `make_vertplus.py --width W --height H` - screen in landscape. It picks Vert+ or Hor+.
  The default is 2480x2248 (the tested target; this game's owner plays it on the Find N6
  rather than at 32:9).
- Eden settings: `eden_settings.py [--async-gpu on|off] [--oppo-refresh-high] [--dry-run]`.

## 7. Install, uninstall, troubleshooting

See [dist/INSTALL.md](dist/INSTALL.md). Release zips are built by `src/package.sh` into
`src/out/`.

## 8. Not covered

- Other game versions (13.0.1/3/4/5). The offsets differ; port with the method below.
- UI/HUD correction (4.3).
- Hor+ hasn't been tested in-game yet.
- Pop-in in the extended view areas, if any stage culls aggressively.

## 9. Discovery method (reusable for other yuzu-family games)

1. Dump `main` with Eden `dump_nso=true`. Map pchtxt offsets: address = offset (with `offset_shift 0x100`).
2. Look at existing aspect mods' patch sites. The projection builder is usually where an
   aspect `ldr`/`fmov` gets replaced.
3. Disassemble with capstone (`src/tools/dis.py <hex addr> [before] [after]`). Find
   `f = 1/tan(fov/2)` and the `P00 = f/aspect` divide.
4. Patch only the final matrix terms, so the game's camera logic stays stock. Fold redundant
   vector moves to make room.
5. To follow C++ objects: `src/tools/rela.py` builds an addend -> offset map from
   `.rela.dyn` (R_AARCH64_RELATIVE). Follow RTTI name -> typeinfo -> vtable -> GOT entry,
   then `src/tools/xref.py <addr>` finds the code that references it.
6. Verify in Eden's log (`Applying IPSwitch patch from mod ...`) and test in a real fight.
