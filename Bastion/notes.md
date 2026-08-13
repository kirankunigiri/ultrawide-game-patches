# Bastion - Ultrawide Patch Notes

Full technical write-up for making **Bastion** run at an ultrawide resolution
(developed for **5120×1440 / 32:9**) with:

- true native render at the target resolution (not upscaled),
- **full-width (hor+) gameplay**,
- HUD, menus, and subtitles at **correct size**, **centered** in a 16:9 band,
- the **parallax backdrop spanning the full width**.

Everything is done by patching `Bastion.exe`. No game files besides the exe are touched.

---

## 1. The game engine

Bastion runs on **FNA** (an open reimplementation of XNA). The game code lives in
`Bastion.exe` as a **managed .NET assembly** in the `GSGE` namespace, and it is
**not obfuscated** - method/field names are intact (`GSGE.App::setLetterBoxViewports`,
`GSGE.Code.GUI.GUIConstants::getResolutionScale`, etc.). That makes it fully
inspectable and patchable with **Mono.Cecil** (IL-level editing).

Key design fact: the UI is authored against a **1920×1080 (16:9) design space**.
The engine scales/positions everything from that base using the *current* screen
dimensions. On a 16:9 monitor this "just works"; on 32:9 several assumptions break.

Two engine-wide screen values (set from the active viewport) drive almost everything:
`GUIConstants.SCREEN_WIDTH` and `GUIConstants.SCREEN_HEIGHT`.

---

## 2. The problems on 32:9 and the fixes

There are **7 edits**. Six are IL patches (resolution-independent); one is a raw-byte
edit to the resolution table (the only resolution-specific part).

### Patch 1 - `GSGE.App::setLetterBoxViewports(int width, int height)`  → full screen
The engine renders the world+HUD into `m_viewport`. Originally it computed a 16:9 box
**from the width**:

```
m_viewport.Width  = width
m_viewport.Height = width * 1080 / 1920        // 16:9 height for that WIDTH
m_viewport.Y      = (height - that) / 2
```

At 5120×1440 that height is `5120*1080/1920 = 2880` - **twice the screen height** -
centered at `Y = (1440-2880)/2 = -720`. The letterbox box spills 720 px off the top
and bottom, so anything anchored to its top/bottom edges is drawn off-screen → the
**HUD was cropped**.

**Fix:** make both `m_fullViewport` and `m_viewport` = `(0, 0, width, height)` (the real
screen). No overflow, full-width gameplay.

### Patch 2 - `GUIConstants::getResolutionScale()`  → height-based
```
original:  return SCREEN_WIDTH  / 1920;   // width-based
patched:   return SCREEN_HEIGHT / 1080;   // height-based
```
This single value scales **both the size and the horizontal spread** of the UI. Width-based
gives `5120/1920 = 2.667×` at 32:9 → the HUD/text are blown up **and** the 1920-wide UI
design space is stretched across the whole screen. Height-based gives `1440/1080 = 1.333×`
= correct native size for a 1440p-tall screen.

> On any 16:9 display `SCREEN_HEIGHT/1080 == SCREEN_WIDTH/1920`, so this is a no-op there
> and only changes behaviour on non-16:9. That's why it's safe.

After this fix the UI is the right *size* but now packs into the **left 16:9 quadrant**
(because the design space maps to `1440*16/9 = 2560` px starting at x=0). Patches 3 & 4 fix that.

### Patches 3 & 4 - horizontal centering
Two methods convert design coords → screen coords and historically only adjusted **Y**
(a "flush" for vertical bottom/center anchoring), never X:

- `GSGE.GUIComponent::setScaledLocation(float x, float y, Flush flush)` - HUD & menus
  (writes the instance field `m_location`).
- `GSGE.GUIComponent::getScaledLocation(float x, float y, Flush flush, float xScale)` -
  subtitles and misc (builds/returns a `Vector2`).

**Fix:** add the horizontal mirror of the engine's own vertical-flush math:

```
X += (SCREEN_WIDTH - scale * 1920) * 0.5     // = +1280 px at 5120x1440
```

This centers the 1920-wide UI design space within the real screen width.

> ⚠️ **Placement matters.** In `getScaledLocation`, the `flush == 2` case does a `br`
> straight to the `ret`, jumping over the tail of the method. The centering **must** be
> inserted **right after the X assignment and before the flush branch**, or `flush == 2`
> callers (**subtitles use flush 2**) silently skip it. `setScaledLocation` was already
> patched before its branch, so it was fine - this bug only bit the subtitles.

### Patch 5 - `GSGE.MapBackground::drawBackdrop(SpriteBatch)`  → width-based backdrop
The parallax backdrop sizes itself with `BackdropScale = Max(1, getResolutionScale())`.
After Patch 2 made `getResolutionScale()` height-based (1.333×), the backdrop only covered
`~2560` px - a 16:9 slice - which looks ugly on 32:9.

**Fix:** in *this method only*, replace the `getResolutionScale()` call with an inline
`SCREEN_WIDTH / 1920` (width-based, 2.667×) so the backdrop fills the full width again.
The backdrop wants **width**-based scaling; the UI wants **height**-based. They were in
tension through one shared function; this splits them at the backdrop's call site.

### Patch 6 - resolution table (raw bytes)  → adds the target resolution
The exe holds two parallel `int32` arrays of selectable resolutions (widths, then heights):

```
widths :  1024,1280,1366,1440,1600,1600,1680,1920,1920, 0
heights:   768,1024, 768, 900, 900,1200,1050,1080,1200, 0
pairs  :  1024x768, ..., 1920x1080, 1920x1200
```

**Fix:** repurpose the last stock slot (**1920×1200**, index 8) → **target W×H**. This keeps
1920×1080 available and makes the new resolution appear in **Options → Video**. This is the
**only** resolution-specific edit.

### Patch 7 - `GSGE.App::Main`  → bake in borderless windowed
Borderless windowed comes from the `-windowed` and `-noborder` command-line flags, which
`Main` parses into the static bools `m_commandLineWindowed` / `m_commandLineNoBorder`. The
parse loop only ever sets these **true** (when the flag is present) and never false.

**Fix:** insert `m_commandLineWindowed = true; m_commandLineNoBorder = true;` at the very
**start** of `Main`, before the parse loop - so the game always launches borderless windowed,
exactly as if `-windowed -noborder` were passed. This removes the need for a launcher `.bat`
or Steam launch options. Pass `--keep-fullscreen` to the patcher to skip this edit and leave
the game's default window mode (still toggleable in Options → Video).

---

## 3. How the patcher works (`src/`)

`src/Program.cs` (a small .NET 8 console app using Mono.Cecil) applies all 7 edits in one run.

Flow:
1. If `<exe>.orig-backup` doesn't exist, copy the exe to it (assumed stock, first run).
2. Otherwise **restore the exe from `.orig-backup`** first - so the patcher is **idempotent**
   and re-running never double-adds the centering offsets.
3. Apply patches 1-5 via Cecil, then `asm.Write(exe)`.
4. Apply patch 6 by raw-byte editing the just-written file (Cecil preserves the stock
   resolution table; we locate the arrays by their stock signature and overwrite slot 8).

The IL patches locate methods by name and **harvest operands** (field/method refs, the
`scale` local, `Vector2::X`) from the existing body, so they don't depend on hard-coded
offsets - just on the method names/shapes, which are stable across builds.

### Running it
```powershell
# from Bastion/src
dotnet run -- --exe "C:\Games\Solo\Bastion\Bastion.exe" --width 5120 --height 1440
```
or use the convenience wrapper:
```powershell
# from Bastion/src
./apply.ps1 -Exe "C:\Games\Solo\Bastion\Bastion.exe" -Width 5120 -Height 1440
```
Defaults are `C:\Games\Solo\Bastion\Bastion.exe` and `5120×1440`.

---

## 4. Adapting to other resolutions / monitors

- The **IL patches are resolution-independent** - they derive everything from `SCREEN_WIDTH`
  / `SCREEN_HEIGHT` at runtime against the fixed 1920×1080 design base. You do **not** need
  to re-patch them for a different ultrawide.
- Only **Patch 6** (the resolution table entry) is specific. Just pass different
  `--width/--height`; the patcher writes them into the 1920×1200 slot. Examples:
  - 3840×1080 (also 32:9): `--width 3840 --height 1080`
  - 5120×2160 (dual-4K 32:9): `--width 5120 --height 2160`
  - 3440×1440 (21:9): `--width 3440 --height 1440`
- The centering math assumes a **wider-than-16:9** screen (it insets the UI). For a screen
  **taller** than 16:9 you'd instead want vertical letterboxing of the UI - not handled here.
- The design constants `1920` and `1080` are the game's, **not** your resolution - leave them.

---

## 5. Known / intentionally not fixed

- **Floating backdrop "flyers":** `GSGE.Code.Things.Flyer::getDrawScale()` also calls
  `getResolutionScale()` and now uses the height-based (1.333×) scale instead of the old
  width-based (2.667×) for the drifting background debris. Not visibly wrong in testing, so
  left alone. If they ever look mis-scaled against the full-width backdrop, apply the same
  width-based swap (`SCREEN_WIDTH/1920`) as Patch 5, in `Flyer::getDrawScale`. Other
  `Things.*` callers of `getResolutionScale()` (e.g. floating damage-number text) are text
  and should **stay** height-based.
- **Menus / fullscreen backgrounds:** menus now center in the 16:9 band; a fullscreen menu
  background becomes a centered 2560-wide image with empty/black sides. Expected and fine.

---

## 6. Discovery methodology (useful for other games)

How the relevant methods were found, in case you adapt this approach to another FNA/XNA game:
1. **Strings/`WSGF`/`PCGamingWiki`** confirmed a hex/exe hack is the route and gave the
   resolution-table concept.
2. Dumped the assembly with Mono.Cecil and searched member names for `Viewport`, `TitleSafe`,
   `Hud`, `Gui`, `LetterBox` → found `GSGE.App` (viewports) and `GSGE.Code.GUI.GUIConstants`.
3. Traced `App::resize` → it feeds `m_viewport` dims to `GUIConstants.resize`,
   `InGameUI.resize`, and `Camera.setSize` (that's the world/HUD coupling).
4. Read `getResolutionScale`, `setScaledLocation`, `getScaledLocation` to find the size &
   position math; used a **callers-of** search on `getResolutionScale` to find every affected
   site (almost all GUI; the world outliers were `MapBackground::drawBackdrop` and
   `Things.Flyer::getDrawScale`).

The exploratory tooling used to do this (a multi-mode Cecil dumper: `find`, `list`, `dump`,
`refs`, `callers`, `types`) isn't shipped here, but the moves above reproduce it.

---

## 7. Troubleshooting

- **"resolution table not found (game version mismatch?)"** - a different Bastion build may
  have a different stock resolution list. Dump the widths/heights arrays and update the
  signature in `PatchResolutionTable`.
- **A method-not-found / operand exception** - a different build renamed or reshaped a method.
  Re-inspect that method's IL and adjust the harvest logic.
- **Game won't launch after patching** - restore a backup (see below) and re-check. The exe
  is a plain managed assembly; the crack in this copy doesn't verify a strong name, so Cecil
  re-writing it is fine.
- **Corrupted / stuck** - restore `Bastion.exe.orig-backup` and run the patcher again.

---

## 8. Backups

The patcher creates `Bastion.exe.orig-backup` (stock) on first run and restores from it on
every subsequent run. Keep that file. During development these staged backups were also made
in the game folder (each keeps the resolution fix unless noted):

| File | State |
|---|---|
| `Bastion.exe.orig-backup` | bone stock |
| `Bastion.exe.res-backup` | resolution only |
| `Bastion.exe.vp-backup` | + viewport fix (oversized HUD) |
| `Bastion.exe.scale-backup` | + size fix (left-clustered UI) |
| `Bastion.exe.centered-checkpoint` | + centered HUD/menus (pre subtitle/backdrop) |

---

## 9. Launch

Just launch the game normally - from Steam, or by running `Bastion.exe`. Borderless windowed
is baked into the exe (Patch 7), so no launcher `.bat` or Steam launch options are needed.
Then select **5120×1440** in **Options → Video** (it replaces the old 1920×1200 slot).

(If you patched with `--keep-fullscreen`, the window mode is whatever the game defaults to /
what you pick in Options → Video.)
