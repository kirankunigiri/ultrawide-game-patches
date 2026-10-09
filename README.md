# ultrawide-game-patches

Patches and tools to make games render and behave correctly at ultrawide /
super-ultrawide resolutions (21:9, 32:9) - full-width gameplay with correctly
sized and positioned UI.

Each game lives in its own top-level folder with a consistent layout.

## Folder structure (per game)

```
<Game>/
  dist/      Files you copy directly into the game's install folder, plus an INSTALL.md
             guide. For a runtime mod this is the built mod itself; for a binary patch
             it is just the guide, since the patch is applied from src/.
  src/       Source needed to produce the fix that isn't a plain drop-in - e.g. a
             patcher program you run against your own game files, the mod source, or
             the script that builds the game's one-zip release.
  notes.md   Full technical write-up: how the fix works, every change and why, how to
             adapt it (other resolutions/monitors), caveats, and troubleshooting.
```

> Modified game binaries are **not** committed (they're copyrighted, and version/
> resolution-specific). Where a fix is a binary patch, `src/` ships the patcher so you
> apply it to your own legally-owned copy. Mods we wrote ourselves *are* shipped built
> in `dist/`, since they are our own code and touch nothing shipped by the publisher.

## Conventions

- **Silent by default.** Fixes write no logs, log files or debug output unless you turn on
  their debug switch (each game's `INSTALL.md` names it). Only turn it on while
  troubleshooting. Third-party loaders (UE4SS, MelonLoader) still keep their own logs.
  Gecko Gods predates this rule and still writes its messages to MelonLoader's log.
- **Your resolution is a setting.** Fixes default to 32:9 (5120×1440) but take your
  resolution or aspect ratio as a setting, so 21:9 works too.
- **One-zip installs where possible.** When a fix needs a mod loader, its release on the
  [Releases page](https://github.com/kirankunigiri/ultrawide-game-patches/releases) bundles
  the exact tested loader build, already configured, plus the mod: extract and play.
- **No game files in the repo** (see above).

Adding or changing a fix (people or AI agents): follow [AGENTS.md](AGENTS.md).

## Game List

| Game | Fix type | Target tested |
|------|----------|---------------|
| [Bastion](Bastion/) | Binary patch (Mono.Cecil) | 5120×1440 (32:9) |
| [Gecko Gods](GeckoGods/) | Runtime mod (MelonLoader / Unity IL2CPP) | 5120×1440 (32:9) |
| [Fatal Claw](FatalClaw/) | Runtime mod (UE4SS Lua / Unreal Engine 4.27) | 5120×1440 (32:9) |
| [Ratchet & Clank: Rift Apart](RiftApart/) | Gameplay helper (external Python overlay): **new minimap**, **fixes shooting while sprinting**, **auto sprint / auto hover** | 5120×1440 (32:9) |

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

### Fatal Claw - what's fixed (tested at 32:9 / 5120×1440, configurable for 21:9)

- **Full-width image** - removes the 16:9 pillarbox the game locks onto every camera, so it renders across the whole screen.
- **Correct field of view (Hor+)** - keeps the game's 16:9 vertical framing and shows more of the world to the sides, instead of the ~2x zoom you get from only removing the bars (gameplay camera 60 -> 98.2 degrees at 32:9).
- **Cutscenes and title intro** - the in-engine cutscenes and the animated title screen set the FOV every frame; every frame is converted, so they're no longer zoomed in.
- **Gate-teleport zoom, no flicker** - the gate's zoom-in and zoom-out are converted frame by frame and stay clean however many times you teleport.
- **No tint seam** - the darkening overlay in front of the gameplay camera is widened to cover the full screen instead of only the middle 16:9.
- **21:9 or 32:9** - set your resolution in `config.lua`; the FOV and overlay math follow your aspect ratio (only 32:9 tested in-game).

**Install: download one zip from [Releases](https://github.com/kirankunigiri/ultrawide-game-patches/releases/tag/fatalclaw-v1.0) and extract it into the game folder** ([FatalClaw/dist/INSTALL.md](FatalClaw/dist/INSTALL.md)). It bundles the exact UE4SS experimental build that was tested (the stable release can't identify this game's engine), already configured. Runtime mod (UE4SS Lua), so **no game files are modified** and it is removed by deleting one folder. Silent unless `Debug = true` in `config.lua`. See [FatalClaw/notes.md](FatalClaw/notes.md), including the gate-teleport flicker post-mortem in section 4.

### Ratchet & Clank: Rift Apart - what's added and fixed (tested at 32:9 / 5120×1440)

Not a rendering fix (the game already handles ultrawide): a gameplay helper that runs next to the game.

- **New minimap** - the game has none. A square HUD minimap (and a fullscreen map on backtick) using the game's own map art, your live position and facing, the explored areas from the game's fog of war, and the collectibles/objective from the pause map with their real icons. Hides itself in menus, cutscenes and store screens. Planets so far: Sargasso, Scarstu Debris Field, Savali, Blizar Prime.
- **Fixes shooting while sprinting** - pressing fire while sprinting could leave you unable to shoot for 1-3 seconds (the character flips between run and aim every frame). The helper detects that native state and clears it: steady fire about 15-30 ms after the click.
- **Auto sprint mode** (default) - sprint turns itself back on whenever you move, including after jumps and dashes, and is dropped while you fire or aim. **Normal mode** (F8) leaves sprint to you but keeps the shooting fix.
- **Auto hover mode (hover boots)** - the game only hovers while Shift is held; the helper turns Shift into a tap-to-start / tap-to-stop hover toggle. Aiming pauses hover; left click stays the hover boost.
- **Starts with the game** - optional auto-start that launches the helper whenever the game runs.

External Python program: reads game memory (read-only) and presses Shift for you, nothing injected and no game files modified. Game art is extracted once from your own install. Silent unless `--debug`. See [RiftApart/dist/INSTALL.md](RiftApart/dist/INSTALL.md) and [RiftApart/notes.md](RiftApart/notes.md).
