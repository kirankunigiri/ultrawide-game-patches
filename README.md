# ultrawide-game-patches

Patches and tools to make games render and behave correctly at ultrawide /
super-ultrawide resolutions (21:9, 32:9) - full-width gameplay with correctly
sized and positioned UI.

Each game lives in its own top-level folder with a consistent layout.

## Folder structure (per game)

```
<Game>/
  dist/      Files you copy directly into the game's install folder, plus an INSTALL
             guide. For a runtime mod this is the built mod itself; for a binary patch
             it is just the guide, since the patch is applied from src/.
  src/       Source needed to produce the fix that isn't a plain drop-in - e.g. a
             patcher program you run against your own game files, or the mod source.
  notes.md   Full technical write-up: how the fix works, every change and why, how to
             adapt it (other resolutions/monitors), caveats, and troubleshooting.
```

> Modified game binaries are **not** committed (they're copyrighted, and version/
> resolution-specific). Where a fix is a binary patch, `src/` ships the patcher so you
> apply it to your own legally-owned copy. Mods we wrote ourselves *are* shipped built
> in `dist/`, since they are our own code and touch nothing shipped by the publisher.

## Game List

| Game | Fix type | Target tested |
|------|----------|---------------|
| [Bastion](Bastion/) | Binary patch (Mono.Cecil) | 5120×1440 (32:9) |
| [Gecko Gods](GeckoGods/) | Runtime mod (MelonLoader / Unity IL2CPP) | 5120×1440 (32:9) |

### Bastion - what's fixed (all at 32:9 / 5120×1440)

- **True native resolution** - adds 5120×1440 as a real render target (not upscaled from 1080p) via the exe's resolution table.
- **Full-width gameplay** - removes the letterbox-viewport overflow that cropped the screen, so the game renders across the entire 32:9 (hor+).
- **No cropped HUD** - HUD elements no longer fall off the top/bottom edges.
- **Correct HUD/text size** - fixes the oversized (2.67×) UI/text by switching UI scaling from width-based to height-based.
- **Centered HUD & menus** - HUD and menu screens are centered in a 16:9 band instead of stretched across the full width or clustered on the left.
- **Centered subtitles** - subtitle text is centered along with the rest of the UI (separate code path from the HUD).
- **Full-width parallax backdrop** - the scrolling background spans the entire 32:9 screen again instead of being squeezed into a 16:9 slice.
- **Borderless windowed baked in** - the exe launches in borderless windowed mode on its own (no launcher `.bat` or Steam launch options). Pass `--keep-fullscreen` to skip this.

Resolution-independent IL patches; only the resolution-table entry is per-resolution. Works on Steam copies too and does **not** touch the save path (Steam Cloud keeps working). See [Bastion/notes.md](Bastion/notes.md) for the technical write-up.

### Gecko Gods - what's fixed (all at 32:9 / 5120×1440)

- **Correct camera framing** - at 32:9 Unity's constant-vertical-FOV default blew the horizontal view out to ~128°, wrecking the composition. The mod rewrites the camera FOV each frame (measured 60.00 -> 32.20) so the game keeps its intended 16:9 horizontal framing while filling the ultrawide screen.
- **Survives Cinemachine** - the game re-sets FOV every frame, so the fix re-applies in `OnLateUpdate` rather than once.
- **Forced ultrawide resolution** - the game was launching 2560×1440 windowed (16:9); the mod puts it in 5120×1440 borderless automatically.
- **Menu / UI scaling** - all `CanvasScaler`s are normalized to match-height so menus keep their vertical framing and expand sideways.
- **Fully configurable** - target resolution, each individual fix, and borderless vs windowed are all togglable in `MelonPreferences.cfg`; no rebuild needed for other ultrawide resolutions.

Runtime mod, so **no game files are modified** and it is removed by deleting one DLL. Unity 6 / IL2CPP means the game's code is compiled and obfuscated, so the mod corrects Unity's own objects at runtime instead of patching game code. See [GeckoGods/notes.md](GeckoGods/notes.md), including the IL2CPP native-crash lesson in section 4.
