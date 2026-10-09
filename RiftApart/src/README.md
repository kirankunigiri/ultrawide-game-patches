# Rift Apart minimap and sprint assistant

Windows/Python external overlay for the inspected RiftApart.exe **3.630.1.0**.
This is a reverse-engineered prototype with map art for **Sargasso**, **Scarstu Debris Field**, **Savali** and **Blizar Prime**.
Player tracking was confirmed working by the user. The native-toggle sprint
assist (Always and Normal modes) was verified live on 2026-10-07; see SPRINT.md.

## Run

Automatic: run ../Install-Autostart.ps1 once (Startup-folder shortcut to
../autostart.pyw, which starts/restarts/stops minimap.py with the game).
`-DebugLogging` passes --debug; `-Remove` uninstalls.

Manual:

Open the game, then run from this directory (assets use relative paths):

```powershell
python minimap.py
```

Runtime dependencies: 64-bit Python (tested with C:\Python312\python.exe),
Tkinter, Pillow, NumPy and pymem. Analysis scripts additionally use pefile,
Capstone, and some older experiments use OpenCV. Asset extraction uses the
bundled ALERT directory. Do not run every Python file as a test: several old
experiments scan large parts of memory or send movement input.

- Backtick opens/closes the fullscreen overlay (with any Ctrl/Alt/Shift/Win held too).
- Open the game's pause map to refresh collectible/objective markers.
- The overlay hides itself during cutscenes and store screens (native hero state).
- F8 switches Always sprint / Normal sprint; selection persists in
  sprint_settings.json. Missing settings default to Always sprint.
- Always sprint restores sprint while moving with WASD, except while left mouse
  (fire) or right mouse (aim) is held. Normal sprint only cancels for fire/aim.
- The game must use toggle sprint on Left Shift. Controller input and remapped
  sprint/movement buttons are not currently supported.
- Small map: 360 px square, radius 190 world units, no caption, inside the
  centered 16:9 bounds with a 60 px right margin and a 180 px top offset.
  Fullscreen: 1050 world units vertically; caption includes sprint mode.

## Read these first

1. **DEVELOPMENT.md**: architecture, recreation workflow, memory and asset formats,
   diagnostics, performance, and current work.
2. **TRACKING.md**: native player resolution, signatures, desync cause and tests.
3. **SPRINT.md**: native toggle discovery and assist state machine.
4. **CLAUDE_HISTORY.md**: summary of the original Claude session. Historical:
   its pointer-chain voting, jump filtering, and 700-unit fullscreen zoom are
   superseded. Do not restore those mechanisms from the historical summary.

## Core files

| File | Purpose |
| --- | --- |
| minimap.py | Launch, map discovery/capture, draw loop, UI and helper lifecycle |
| overlay.py | Transparent, click-through Tk window |
| mem.py | Process/module attachment, ReadProcessMemory, region enumeration |
| player_tracking.py | Platform-independent validated native hero reader |
| heroread.py | Running-game adapter for the hero reader |
| hero_states.py | Native cutscene/store state check used to hide the overlay |
| sprint_assist.py | Native sprint-toggle reader, mode policy, Windows key pulses |
| arr.py | Pause-map icon record decoder |
| fogread.py | Native explored-cell table and bit grid |
| extract_assets.py | One-time extraction of map art and icons from the user's install |
| maps.json | Per-planet registry: native map id -> extracted texture + exact bounds |
| maps/, icons/ | Extracted game artwork used by the renderer |
| test_player_tracking.py, test_sprint_assist.py | Isolated memory/policy tests |
| state_probe.py, comp_dump.py | Live probes; state_probe moves the character (see SPRINT.md) |

Run focused tests without opening the game:

```powershell
python -m unittest test_player_tracking test_sprint_assist -v
python -m py_compile minimap.py sprint_assist.py
```

The active project is RiftApart/src in the ultrawide-game-patches repository.
The original Claude scratchpad is retained as a backup. Local extracted artwork,
captures, memory dumps and runtime state are Git-ignored; preserve them locally.
