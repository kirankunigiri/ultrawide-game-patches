# Fatal Claw Ultrawide (21:9 / 32:9) - Install

A UE4SS Lua mod. No game files are modified - UE4SS loads alongside the game and the mod
corrects the cameras at runtime: full-width image, correct field of view, cutscenes, the
gate-teleport zoom and the camera tint overlay.

Tested at 5120x1440 (32:9) on Fatal Claw (Unreal Engine 4.27, Windows build dated
2026-08-26) with UE4SS experimental build `v3.0.1-1152-ge3ba1016`. 21:9 runs the same code
with a different aspect ratio but hasn't been tested in-game.

## Quick install (recommended)

1. Download **[FatalClaw-Ultrawide-v1.0.zip](https://github.com/kirankunigiri/ultrawide-game-patches/releases/download/fatalclaw-v1.0/FatalClaw-Ultrawide-v1.0.zip)**
   (from the [fatalclaw-v1.0 release](https://github.com/kirankunigiri/ultrawide-game-patches/releases/tag/fatalclaw-v1.0)).
2. Extract it into your Fatal Claw folder - the one that contains `FatalClaw.exe`. Allow it
   to merge into the existing `FatalClaw` folder.
3. **21:9 only:** open `FatalClaw\Binaries\Win64\ue4ss\Mods\UltrawideFix\Scripts\config.lua`
   and set `ScreenWidth` / `ScreenHeight` to your resolution (see [Configuration](#configuration)).
   32:9 at 5120x1440 needs no changes.
4. Play. Run the game at your monitor's native resolution (tested: fullscreen windowed).

The zip contains UE4SS (unchanged except for two settings: engine version 4.27 and its
bundled example mods turned off) and the UltrawideFix mod, all under
`FatalClaw\Binaries\Win64\`. It is built by [`../src/package.ps1`](../src/package.ps1).
UE4SS is MIT-licensed; its license is included at `ue4ss\LICENSE`.

## Configuration

`FatalClaw\Binaries\Win64\ue4ss\Mods\UltrawideFix\Scripts\config.lua` (save, then restart
the game):

| Key | Default | Meaning |
|---|---|---|
| `ScreenWidth` / `ScreenHeight` | `5120` / `1440` | Your resolution; sets the aspect ratio the fix targets |
| `FovScale` | `1.0` | 1.0 = the game's 16:9 vertical view, wider. Above 1.0 zooms out further, below zooms in (0.5 - 2.0) |
| `Debug` | `false` | `true` = log what the mod does to `ue4ss\UE4SS.log` |

Common resolutions:

| Aspect | Resolutions |
|---|---|
| 32:9 | 5120 x 1440 (default), 3840 x 1080 |
| 21:9 | 3440 x 1440, 2560 x 1080, 3840 x 1600 |

The mod is silent: it writes nothing anywhere unless `Debug = true`. UE4SS itself still
keeps its own `ue4ss\UE4SS.log`. If the screen isn't wider than 16:9, the mod switches
itself off.

## Uninstall

In `<game>\FatalClaw\Binaries\Win64\`:

- Remove the fix only: delete `ue4ss\Mods\UltrawideFix`
- Remove everything: delete `dwmapi.dll` and the `ue4ss` folder

Nothing else is changed, so the game is back to stock (16:9 with side bars).

## Manual install (if you already use UE4SS)

1. **UE4SS experimental build.** Get `UE4SS_v3.0.1-1152-ge3ba1016.zip` (or newer) from
   [UE4SS experimental-latest](https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest) -
   not the `zDEV-` / `zCustomGameConfigs` / `zMapGenBP` files. Don't use the stable v3.0.1
   release: it can't identify this game's engine ("PS scan timed out" in `UE4SS.log`).
   Extract it into `<game>\FatalClaw\Binaries\Win64\` so `dwmapi.dll` and `ue4ss\` sit next
   to `FatalClaw-Win64-Shipping.exe`.
2. **Engine version (required).** In `ue4ss\UE4SS-settings.ini`:
   ```ini
   [EngineVersionOverride]
   MajorVersion = 4
   MinorVersion = 27
   ```
3. **Example mods off (recommended).** Set every entry in `ue4ss\Mods\mods.txt` to `0` and
   every `"mod_enabled"` in `ue4ss\Mods\mods.json` to `false`. The fix was tested with all
   of them off.
4. **The mod.** Copy the [`UltrawideFix`](UltrawideFix) folder into `ue4ss\Mods\`
   (`enabled.txt` switches it on; no `mods.txt` entry needed), then set your resolution in
   its `Scripts\config.lua`.

## Troubleshooting

Turn on `Debug = true` in `config.lua` first. The mod then writes `[UltrawideFix]` lines to
`ue4ss\UE4SS.log`, starting with one that shows the resolution it uses and where its
settings came from. Turn it off again when done.

| Symptom | Cause |
|---|---|
| No `UE4SS.log` at all after launching | `dwmapi.dll` isn't next to `FatalClaw-Win64-Shipping.exe` - the zip wasn't extracted into the folder with `FatalClaw.exe` |
| `UE4SS.log` ends with "PS scan timed out" | Engine version override missing, or the stable UE4SS release is installed (manual install steps 1-2) |
| No `Mod 'UltrawideFix' has enabled.txt` line in `UE4SS.log` | Mod folder in the wrong place or `enabled.txt` missing |
| Debug log says "settings from defaults", or `Debug = true` writes nothing | `config.lua` has a typo and couldn't be read; the mod uses 5120x1440 with Debug off. Every setting line ends with a comma |
| Picture too zoomed in / out | `ScreenWidth` / `ScreenHeight` don't match the resolution the game runs at |
| Side bars still there | The game isn't running at an ultrawide resolution, or UE4SS / the mod isn't loading |

See [../notes.md](../notes.md) for how the fix works.
