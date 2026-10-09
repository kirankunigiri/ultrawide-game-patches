# Ratchet & Clank: Rift Apart - minimap and sprint/hover helper

An external Python helper that runs next to the game. It reads the game's memory
(read-only) and draws an overlay; for sprint and hover it presses Shift for you.
Nothing is copied into the game folder and no game file is modified.

Tested on the Steam build of RiftApart.exe 3.630.1.0 at 5120x1440 (32:9),
borderless/fullscreen, keyboard and mouse.

## Quick install

1. Install 64-bit Python 3.12 (with Tkinter, the default) and the packages:
   ```
   pip install -r RiftApart/src/requirements.txt
   ```
2. Get the asset extractor (used once, to pull the map art from your own copy of the
   game; game art is not shipped in this repo):
   ```
   git clone https://github.com/Tkachov/ALERT RiftApart/src/ALERT
   ```
   For full-resolution planet maps, also take `Overdrive/libdeflate.dll` from ALERT's
   [v0.4.0 release zip](https://github.com/Tkachov/ALERT/releases/tag/v0.4.0-overdrive)
   and put it in `RiftApart/src/`. Without it, maps other than Sargasso are 512 px.
3. Extract the art (pass your game folder if it is not
   `C:\Games\Solo\Ratchet & Clank Rift Apart`):
   ```
   cd RiftApart/src
   python extract_assets.py "D:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart"
   ```
4. In the game's controls, keep sprint on **Left Shift** set to **toggle**, WASD movement,
   left mouse fire, right mouse aim (the defaults).
5. Run `RiftApart/Install-Autostart.ps1` once. From then on the helper starts by itself
   whenever the game is running and stops when it closes. For a one-off start instead,
   run `RiftApart/Start.ps1`.
6. In game, open the pause map once per planet so the minimap picks up collectibles.

## Controls and configuration

- **Backtick (`)** opens/closes the fullscreen map, with any other keys held.
- **F8** switches **Always sprint** (default) and **Normal sprint**; the choice is saved in
  `src/sprint_settings.json`.
- **Always sprint:** sprint turns itself back on while you move with WASD, including after
  jumps and dashes. Fire (left mouse) or aim (right mouse) turns it off, and it comes back
  about 0.15 s after release.
- **Normal sprint:** you toggle sprint yourself; fire/aim still turn it off.
- **Both modes** fix the game's fire-while-sprinting lock (fire pressed while sprinting
  could leave you unable to shoot for seconds).
- **Hover boots:** once the helper sees you hover, Shift becomes a hover toggle in Always
  mode (tap to start, tap to stop; the game itself only hovers while Shift is held).
  Right click (aim) pauses hover; left click stays the hover boost. Normal mode leaves
  hover to the game.
- The minimap hides during cutscenes, store screens, the pause map, and where the map is
  offline or the planet has no art yet (see `src/maps.json`: Sargasso, Scarstu Debris
  Field and Savali so far).
- **Resolution:** the overlay follows your desktop resolution and keeps the minimap inside
  the centered 16:9 area, so 21:9 (3440x1440) uses the same placement; only 32:9 was
  tested in game. Size, zoom and margins are constants at the top of `src/minimap.py`.
- **Debug logging** is off by default and nothing is written. `Start.ps1 -DebugLogging`,
  `Install-Autostart.ps1 -DebugLogging` or `python minimap.py --debug` turn it on (console
  output, plus `minimap.stdout.log` under autostart, and `sprint_lock.log` /
  `minimap.hang.log`, all in `RiftApart/research/`). Saved state that is not logging: `minimap_icons.json`,
  `map_scales.json`, `map_scale_snaps.json`, `facing_offset.json`, `sprint_settings.json`.

## Uninstall

Run `RiftApart/Install-Autostart.ps1 -Remove` (removes the Startup shortcut and stops the
launcher), then stop the Python process running `minimap.py`, and delete the folder.

## Manual use

Start one copy from `RiftApart/src`: `python minimap.py` (or `pythonw minimap.py` for no
console). The auto-launcher never starts a second copy next to one you started yourself.

## Troubleshooting

- **No minimap:** check you are on a planet listed in `src/maps.json` and that
  `src/maps/` and `src/icons/` exist (step 3). It also hides while the game is not the
  foreground window.
- **No collectibles:** open the pause map. On a new planet the first opening uses an
  estimated scale; a second opening ~10 steps away measures it exactly.
- **Sprint never turns on:** the game's sprint must be toggle (not hold) on Left Shift.
- **Anything else:** run with debug logging and look in `RiftApart/research/`
  (`minimap.stdout.log`, `sprint_lock.log`, `minimap.hang.log`).
- Another game build (an update) changes the code the helper checks; the affected part
  turns itself off rather than guessing. See `src/DEVELOPMENT.md` to re-derive it.
