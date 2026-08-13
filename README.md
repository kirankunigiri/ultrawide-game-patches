# ultrawide-game-patches

Patches and tools to make games render and behave correctly at ultrawide /
super-ultrawide resolutions (21:9, 32:9) - full-width gameplay with correctly
sized and positioned UI.

Each game lives in its own top-level folder with a consistent layout.

## Folder structure (per game)

```
<Game>/
  dist/      Files you copy directly into the game's install folder (e.g. launchers,
             configs). For games whose fix is a binary patch, this holds the launcher
             plus an INSTALL guide; the exe patch itself is applied from src/.
  src/       Source needed to produce the fix that isn't a plain drop-in - e.g. a
             patcher program you run against your own game files. Not required at play time.
  notes.md   Full technical write-up: how the fix works, every change and why, how to
             adapt it (other resolutions/monitors), caveats, and troubleshooting.
```

> Modified game binaries are **not** committed (they're copyrighted, and version/
> resolution-specific). Where a fix is a binary patch, `src/` ships the patcher so you
> apply it to your own legally-owned copy.

## Game List

| Game | Fix type | Target tested |
|------|----------|---------------|
| [Bastion](Bastion/) | Binary patch (Mono.Cecil) | 5120×1440 (32:9) |

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
