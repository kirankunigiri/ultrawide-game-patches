# Ratchet & Clank: Rift Apart - Minimap and Sprint/Hover Helper Notes

Technical write-up for a **gameplay helper**, not a rendering patch: the game already
runs correctly at 5120x1440 (32:9). The helper adds an on-screen minimap that shows the
pause map's collectibles, fixes the game's fire-while-sprinting lock, and adds auto
sprint and a hover-boots toggle.

It is an **external Python program** (overlay window + memory reads + Shift key
presses). Nothing is injected into the game, no game file is modified and no game memory
is written. Install: [dist/INSTALL.md](dist/INSTALL.md).

Deeper documents, all in `src/`:
[DEVELOPMENT.md](src/DEVELOPMENT.md) (architecture, every address, how to recreate it),
[TRACKING.md](src/TRACKING.md) (player position),
[SPRINT.md](src/SPRINT.md) (sprint, the fire lock, hover, live test results),
[README.md](src/README.md) (file map),
[CLAUDE_HISTORY.md](src/CLAUDE_HISTORY.md) (how the first version was found; partly superseded).

---

## 1. The game

| | |
|---|---|
| Build | RiftApart.exe **3.630.1.0** (Steam), Insomniac engine, DirectX 12 |
| UI | Coherent GT (HTML/JS UI); the pause map's icons live in native binding records |
| Assets | `toc` + archives; textures read with [ALERT](https://github.com/Tkachov/ALERT) (dat1lib), HD streams GDeflate-compressed |
| Tested | 5120x1440, keyboard and mouse, toggle sprint on Left Shift |

The game has a full pause map (collectibles, objective, explored areas) but no minimap,
so finding collectibles means opening the menu over and over.

---

## 2. What the helper does

### Minimap
- **Real map art** per planet: the game's own map textures, extracted once from the
  player's install (`src/extract_assets.py`), placed with each map's exact world bounds
  from the game's fog-of-war record. `src/maps.json` lists the supported planets
  (Sargasso, Scarstu Debris Field, Savali); others hide the minimap until added.
- **Live player position and facing** from the same native hero entity the pause map
  uses (handle -> entity pool -> transform, generation-checked; TRACKING.md).
- **Explored areas** from the game's own fog grid, drawn in the pause map's style.
- **Collectibles and objective** captured from the pause map's icon records whenever the
  map is opened, converted to world positions and drawn with the game's icon art.
  The pause-map scale is measured per planet from two openings.
- **Fullscreen view** on backtick (any modifiers), square 70% opacity minimap otherwise.
  Hides for the pause map, cutscenes, store screens and map-offline areas.

### Sprint and hover
- **Fire-while-sprinting lock fixed.** If fire is pressed while sprinting and the game
  handles the click first, it clears the sprint toggle but keeps a latent sprint and
  flips between run and aim states every frame, so the weapon barely fires (1-3 s for
  the owner). The helper detects this from native state and clears it with one Shift
  press: steady fire 15-32 ms after the click.
- **Always sprint (default)**: sprint comes back on while moving, after jumps and dashes,
  and after fire/aim release. **Normal sprint** (F8) only cancels for fire/aim.
- **Hover boots**: hover only lasts while Shift is held. In Always mode, a Shift tap
  starts or stops hover and the helper holds the key in between; aim pauses it, left
  click stays the hover boost.

---

## 3. How it works (summary)

- **Reads only.** `mem.py` uses ReadProcessMemory. Every native layout is fingerprinted
  against the exact instructions it was derived from; on a different build the affected
  reader turns itself off.
- **Sprint state** is the run state's input toggle (+0x1CF on HeroStateRunLocal, flipped
  by the game's own sprint routine), found through the hero's component table. Classes
  are told apart by RTTI (run, hover, landing, other). Cutscene/store detection is the
  HeroStateCinematic state. Details and every RVA: SPRINT.md / DEVELOPMENT.md.
- **Input** is ordinary SendInput Shift presses; the game performs its normal transition.
  Physical vs our own Shift is told apart with Windows Raw Input (injected input has no
  device handle), not a keyboard hook.
- **Overlay** is a transparent click-through Tk window. The fog style is pre-applied to
  the whole texture off-thread and pre-scaled per zoom, so a frame is a crop: about 10 ms
  fullscreen, 2 ms minimap; backtick-to-screen 15-45 ms.
- **Auto-start**: `Install-Autostart.ps1` adds a Startup shortcut to `autostart.pyw`,
  which starts the helper with the game, restarts it if it dies and stops it when the
  game closes.

---

## 4. Lessons

- **Find the code that already consumes the data.** Player position from scanned memory
  copies desynced after section transitions; reading the exact entity the pause map uses
  fixed it for good.
- **Animation flags are not input state.** The first sprint reader used a locomotion
  animation flag; the real toggle is the one the input routine flips.
- **Record, then replay.** The fire lock and the hover behaviour were only understood
  after logging native state every few ms while playing, then replaying the log through
  the decision logic offline.
- **Hold vs tap matters.** With hover boots a tap gives a 0.2 s hover; the game only
  hovers while Shift is held.
- **Watch the fixed cost per frame.** Re-styling a 5120x1440 image every frame made the
  fullscreen toggle take 350 ms; doing it once per fog change made it 10 ms.

---

## 5. Configuration

See [INSTALL.md](dist/INSTALL.md): F8 mode, backtick, debug switch (`--debug` /
`-DebugLogging`, off by default, nothing written when off), resolution (follows the
desktop; minimap stays in the centered 16:9 area; only 32:9 tested). Saved state (not
logs): marker captures, pause-map scales, facing offset, sprint mode, hover boots.

---

## 6. Not covered

- Planets other than Sargasso, Scarstu Debris Field and Savali (texture pairing is
  verified per planet; Nefarious City, Blizar Prime and Zordoom textures are known).
- Controller input and remapped sprint/movement keys.
- Other game builds (the readers disable themselves; addresses must be re-derived).
- 21:9 is computed but not tested in game.
- Rare remaining fire locks are being recorded (`sprint_lock.log` in debug mode).

---

## 7. Discovery method (reusable)

1. Start from the UI that already shows the data (pause map), find its bindings and the
   native code that fills them (`xrefs.py`, `disasm.py`, `bindings.py`, `func.py`).
2. Follow that code to the source objects; reproduce small lookups externally instead of
   calling game functions.
3. Use RTTI (`rtti.py`) to name components and find each class's type descriptor
   (vtable slot +0x48 getter).
4. Fingerprint every instruction a layout came from; disable on mismatch.
5. Verify live with balanced, self-returning input scripts (`state_probe.py`) and a
   safety stop, and record real play (`glitch_log.py`, `state_watch.py`).
