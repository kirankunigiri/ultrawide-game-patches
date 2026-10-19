# Infinity Blade II & III (Android port) - filling screens squarer than 3:2

## The game

Infinity Blade II (2011) and III (2013), ChAIR's Unreal Engine 3 iOS games, delisted in 2018. They
run on Android through [jelqedagain/ib-2-3-android](https://github.com/jelqedagain/ib-2-3-android)
(MIT): an iOS runtime that loads the player's own `.ipa` and runs the game's ARM64 code natively,
with UIKit, OpenGL ES, audio and the file system re-implemented. One codebase, two apps:
`com.ib2port.game` and `com.ib3port.game`.

Tested on: port commit `9d707aa` (2026-10-17, IB2 1.9.6 / IB3 1.9.5), IB2 Community Patch v2.5 `.ipa`
(1.3.5, `SwordGame.xxx` package version 864), IB3 Community Patch v2.5.1 `.ipa` (1.4.4, package
version 868), OPPO Find N6 (CPH2765, Android 16, ColorOS 16.0.10.500) inner screen 2480x2248.

## The problem

On the Find N6's inner screen (2480x2248, about 1.1:1) both games show a letterboxed picture:

- **IB2** with Settings > Screen = Full screen: a 16:9 picture across the width, with about a fifth
  of the screen black above and below.
- **IB3**: a 3:2 picture with smaller bars, the HUD squeezed into the same band.

Three separate limits cause it, all from the iPhone/iPad era:

1. **The port** (`src/port/android/app.cpp`) emulates an iPhone screen 414 points tall. IB3 gets the
   window's width (`414 * aspect`); IB2 only gets it on phones *longer* than 16:9 (its widescreen
   patch, `game/widescreen.cpp`). On anything narrower IB2 stays at 736x414 (16:9).
2. **The HUD layout script**, `GameViewportClient.AdjustHUDRenderSize` (`SwordPC` in both games). IB2
   lays the HUD over the whole screen only for aspect ratios in (1.7, 1.8) or exactly 1.5; anything
   else is "an iPad" and gets a 3:2 HUD as wide as the screen. IB3 does the same below 1.5
   (`float(FullScreenSizeX) / float(FullScreenSizeY) <= 1.5`).
3. **The camera**, `SwordCamera` (the same in both games). `InitializeFor` ends with
   `bIsWideAspectRatio = DeviceAspectRatio > 1.5`, and `UpdateViewTarget` adapts the view only then:
   ```
   if (bIsWideAspectRatio) {
       OutVT.POV.FOV = OutVT.POV.FOV / OutVT.AspectRatio * DeviceAspectRatio;
       OutVT.AspectRatio = DeviceAspectRatio;
   }
   ```
   On a squarer screen the view keeps the camera's own 3:2 aspect ratio, which the engine letterboxes.

Removing only (1) and (2) gives a full-screen HUD over a still-letterboxed 3:2 view. All three have to
go.

## The fix

One patch to the port (`src/squarer-screens.patch`, 4 files). Like the port's existing widescreen fix,
it never changes the installed game: it serves the game a patched copy of its script package
(`CookedIPhone/SwordGame.xxx`) from `Library/Caches/port`, made at every launch, and only on a screen
squarer than 3:2. Every patch looks for its bytecode by pattern and requires exactly one match; if any
required one is missing, that game keeps its stock layout.

### Both games: the camera (`fill_squarer_view`)

- `InitializeFor`: the `1.5` in `DeviceAspectRatio > 1.5` becomes `0.5`, so the view always takes
  the screen's shape (`OutVT.AspectRatio = DeviceAspectRatio`).
- `UpdateViewTarget`: the FOV line's `/` and `*` become `FMax`:
  `FMax(FMax(FOV, AspectRatio), DeviceAspectRatio)` is just `FOV` (degrees against ratios around 1-2),
  so the field of view stays as it is at 3:2. UE3's FOV is horizontal, so the view keeps its 3:2 width
  and gains height: what you see at 3:2, plus more above and below. Keeping the original
  `FOV / 1.5 * 1.1` would zoom in and crop the sides by about a quarter.

### IB2

- `app.cpp`: on screens squarer than 3:2 IB2 gets the window's width too (`457x414` points at
  2480x2248), with Settings > Screen = Full screen. Screens from 3:2 to 16:9 are left alone: the iPad
  HUD would run off the top and bottom there.
- `AdjustHUDRenderSize`: besides the port's raised `1.8` bound, the `1.7` becomes `0.5`, so the HUD
  covers the whole screen (16:9 branch). Touch zones follow the HUD; world taps (move circles) and the
  block button were tested.
- Menu backdrops (`IB2_InventoryMenu`, the port's `scale_backdrops`) are scaled by
  `(16/9 / aspect) * (16/9 / 1.55)` (1.85 at 2480x2248) to cover the taller view.

### IB3

- The HUD keeps IB3's own iPad layout (a 3:2 band across the middle). Lowering its `<= 1.5` limit too
  put the HUD over the whole screen, but then the markers it draws over the world, like the move
  circles, landed in the wrong place (drawn over the throne, while the tap target stayed on the
  stairs), and tapping where they were drawn did nothing.
- `SwordMenuAnimScene.RenderIPadBars` masks the screen above and below the HUD band with two black
  bars 80 high (`SetPos(0, -80)`, `DrawRect(ClipX, 80)`, `SetPos(0, ClipY)`, `DrawRect(ClipX, 80)`).
  On an iPad they lie over the camera's letterbox; with a full-screen view they cut black strips into
  every fight. Their height becomes `0`.
- `SwordHudMain.DrawVignette` darkens the exploring view's edges (high detail only) with an icon laid
  over the HUD band, so the strips above and below were lighter. Its `GetDetailMode() >= 2` becomes
  `>= 255`: no vignette, as on lower detail settings. Optional: if not found, the rest still applies.
- The port's Dev Mod `.ipa` fix (`game/devipa.cpp`) already serves IB3's `SwordGame.xxx` and deletes
  any other copy at the same path when the `.ipa` is not the Dev Mod. The IB3 patch therefore runs
  inside it (`fill_ib3_squarer_screen`), on one copy that carries both fixes.

## Lessons

- **Patched UnrealScript must keep its in-memory size.** The first camera patch replaced the
  `DeviceAspectRatio` operand (`01 <ref>`, 5 bytes on disk) with a float constant (`1e <f32>`, also 5)
  and the game aborted: "Execution beyond end of script in Function SwordGame.SwordCamera:
  UpdateViewTarget". Object references are 4 bytes in the package but 8 in memory on 64-bit, and the
  loader re-sizes the script token by token. Swap one-byte tokens (natives like `*` 0xAB, `/` 0xAC,
  `FMax` 0xF5) or same-type constants instead.
- **The screen, the HUD and the camera are three different gates** (see the problem). Check the 3D
  view separately from the HUD: a full-screen HUD over a letterboxed view looks almost fixed.
- **Test world taps, not just buttons.** IB3's "!" button worked with a full-screen HUD while every
  move circle was dead; only comparing with the stock app at the same spot showed it.
- **Two fixes serving the same file must be one.** The port overrides a bundle file by path; a second
  patcher writing the same path (or deleting it) silently undoes the first.
- **Measure, don't eyeball.** The faint strips in IB3 turned out to be lighter outside the HUD band,
  not darker (screenshot row means 45 vs 28 at the top edge, 117 vs 82 at the bottom), which pointed
  at an overlay drawn inside the band rather than a bar drawn outside it.

## Configuration

None. The shape is read from the window when the game starts; screens squarer than 3:2 get the fix,
others behave like the official port. IB2's Settings > Screen = 16:9 turns it off. On a foldable the
shape is read once per launch.

No log output of its own and no debug switch: the patch adds no log lines. The port's own
`ib3rt.log` (always on, outside this fix) keeps its existing `widescreen:` lines, which now also
appear for IB2 on squarer screens.

## Install

[dist/INSTALL.md](dist/INSTALL.md): APKs on the
[infinityblade-v1.0 release](https://github.com/kirankunigiri/ultrawide-game-patches/releases/tag/infinityblade-v1.0),
built by `src/build.sh` from the port at `9d707aa` plus `src/squarer-screens.patch`. They are signed
with a key of ours, not the port developer's, so the official app has to be uninstalled first (back
up saves in the app).

## Not covered

- Pre-rendered videos (both intros) and IB2's in-engine cutscenes (16:9 cinematic cameras) keep their
  bars. IB3's in-engine cutscenes fill the screen.
- IB3's HUD stays in its 3:2 band (see above).
- Only 2480x2248 was tested in-game. 4:3 and 16:10 tablets take the same path; 3:2 to 16:9 screens and
  longer phones are unchanged.
- Only the Community Patch `.ipa`s above were tested; stock 1.3.5 / 1.4.4, IB3 Community Patch v3.0.1
  and the Dev Mod `.ipa`s are untested (the patterns are expected to match; if not, the stock layout
  stays).
- IB2 menus and the Character screen were checked; IB3's menus were not.

## Discovery method (reusable for other UE3 mobile games)

1. Pull the game's script package (`CookedIPhone/SwordGame.xxx`, uncompressed in these builds).
2. `src/tools/find_floats.py SwordGame.xxx 1.5 1.7 1.8` lists the functions that use those float
   constants (`EX_FloatConst` 0x1E), via the export table (`src/tools/upk.py`). Aspect-ratio limits
   show up in `AdjustHUDRenderSize` and `SwordCamera.InitializeFor`.
3. `find_floats.py SwordGame.xxx --dump SwordCamera.UpdateViewTarget` hex-dumps a function with its
   object references resolved; read the bytecode by hand (UE3 tokens: `0x0F` let, `0x14` let bool,
   `0x07` jump-if-not, `0x01` instance variable, `0x00` local, `0x35` struct member, `0x1C` final
   function, `0x16` end of parameters, natives `0xAB`/`0xAC`/`0xB0`-`0xB2` float `* / < > <=`).
4. Find names for the visible symptom (`RenderIPadBars`, `DrawVignette`, `bIsWideAspectRatio`) in the
   name table and every function that references them.
5. Patch with same-size changes only, anchored on a pattern that matches once; compare against the
   stock app at the same spot in the game.
