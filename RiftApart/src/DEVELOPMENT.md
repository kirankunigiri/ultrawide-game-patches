# Developer handoff and recreation guide

Updated 2026-10-07. Read current source together with this document. Native
addresses are observations for one executable build, not a public API.

## Origin and evidence

Claude created the overlay by extracting game map/icon assets, identifying the
pause-map records and fog builder, calibrating world/map transforms, and initially
scanning player-position copies. A Luna subagent summarized that transcript;
the summary is preserved as CLAUDE_HISTORY.md.

Original transcript on this machine:
`C:\Users\KIRAN\.claude\projects\C--Users-KIRAN-Downloads-MIO-Memories-in-Orbit-InsaneRamZes\7cab1995-945b-4d68-8c5b-3fb2a776b83b.jsonl`.
The active runtime project is now `RiftApart/src` in
`C:/Users/KIRAN/Code/ultrawide-game-patches`. The original scratchpad is a backup.
Game executable: `C:\Games\Solo\Ratchet & Clank Rift Apart\RiftApart.exe`.

Codex replaced player-pointer voting with the actual native pause-map hero
resolution path after a reproduced section-transition desync. The user confirmed
that tracking worked. Subsequent work added sprint cancellation and found that
the first sprint reader used an animation flag, not the input toggle. Detailed
addresses and the distinction are in TRACKING.md and SPRINT.md.

## Architecture and process boundaries

`python minimap.py` attaches to the running game's PID, imports the rendering
assets, starts the sprint worker, and runs the Tk overlay. The draw callback runs
nominally every 50 ms (render time adds to that interval). Hero tracking, icons
and exploration use ReadProcessMemory. The helper sends ordinary Windows
keyboard input. There is no DLL injection, remote thread, game-code patch or
game-memory write in the current implementation.

mem.py uses pymem for attachment and module lookup and ctypes for memory reads.
Its `read(address, size)` returns bytes or None; callers should require exact
length before unpacking. Pymem attachment itself does not enforce a read-only
handle permission: “read-only” here describes the operations we perform.
ASLR changes the executable base between launches. Compute live addresses as
`EXE.lpBaseOfDll + RVA`; never copy a heap address from an old diagnostic.
Static disassembly commonly uses preferred image base 0x140000000.

The minimap publishes a timestamped gameplay context to the sprint worker.
The worker requires foreground PID equality, fresh draw heartbeat (under 0.75 s),
no native pause map, and no cutscene/store state (the fullscreen overlay does not pause
sprint or hover: it is only a view). Those checks are conservative
gates, not a universal native “gameplay enabled” flag. Other menus may need
additional guards if an active run component survives while they are displayed.

## Recreating the player hook without injection

1. Find native code that already consumes the data you need. The pause-map player
   marker is preferable to guessing which of many matching XYZ copies is live.
2. Read PE sections and strings, follow RIP-relative references, then inspect
   calls from the map routine. See xrefs.py, disasm.py, bindings.py and func.py.
   xrefs.dis returns text; print it. Start decoding at an established instruction
   or function boundary; disassembly from the middle of an instruction is garbage.
   PE .pdata entries can help locate code boundaries, but some entries represent
   chained function fragments rather than complete functions.
3. At pause-map RVA 0x5EC8D0, the code takes the handle at 0x6003E88, calls resolver
   0xF1A520 and position getter 0x29F7C0. Reproduce the small resolver/getter reads
   externally rather than invoking the functions in an arbitrary remote thread.
4. Decode the handle index/generation, verify the entity pool and generation,
   read its transform, then revalidate identity. See TRACKING.md for every field.
   Position and heading must come from the same transform snapshot.
5. Fingerprint the relevant executable instructions before trusting the layout.
   Missing or changed code must disable that reader rather than silently guessing.
6. Build fake-memory tests for short reads, recycled entities, relocation, races,
   null pointers and genuine large teleports. Live validation is still needed:
   walk, turn, jump, cross a section boundary, respawn, and restart the game.

Old chain/scan experiments remain for archaeological reference. Their agreement
is not proof: several chains can resolve to the same recycled scratch buffer,
so a majority can be confidently wrong. Do not reinstate the stale-position
fallback or reject legitimate teleports with a “maximum distance” heuristic.

## Components, RTTI and native sprint research

An entity's component table is at +0x80 (pointer) and +0x88 (uint16 capacity).
Type descriptors are executable-relative addresses. Native lookup RVA 0xFFB860
uses `(descriptor >> 4) & (capacity - 1)`, 16-byte key/value entries and bounded
linear probing. Classes can be registered under several base descriptors;
presence depends on the active state. A standing relaxed-idle character may
have no run component at all. Never reuse the last run pointer after it disappears.

For MSVC RTTI, an object's first QWORD is usually its vtable; vtable[-1] points
to the Complete Object Locator. For signature 1, its type-descriptor RVA is at
+0x0C; the type name starts at executable base + that RVA + 0x10.
rtti.vtables_for locates class vtables in the PE. rtti.instances performs a
heap scan and is an investigation tool, not part of runtime tracking.

Useful names: HeroStateRun, HeroStateRunLocal, HeroPointerCache, HeroMacroState,
HeroButtonCache and HeroLocal (many are under the Hero namespace). Component
owner is checked at +0x10. Function addresses in a vtable must be validated,
not inferred from a class name alone.

The movement-animation sprint boolean (+0x147 in HeroStateRun) flickers during
fire. The actual local-run toggle is +0x1CF in HeroStateRunLocal. The input
routine at 0x7DEAF0 flips it and calls 0x6C68B0, which updates weapon/macro sprint
state. Full branch evidence and fingerprints are recorded in SPRINT.md.
Native start/stop notifications are downstream consequences, so sending a
notification is not equivalent to performing the transition.

## Hiding during cutscenes and the store

hero_states.py checks the hero's component table for HeroStateCinematicLocal and
HeroStateCinematicMoveLocal. Both cutscenes and vendor/store screens put the hero in
HeroStateCinematic (verified live 2026-10-07; the game has no store-specific hero
state). The overlay hides and sprint assist idles while one is active.
Type descriptors come from the class vtable: slot +0x48 is a getter
`lea rax, [descriptor]; ret`. Resolve new states with rtti.vtables_for("<Class>@Hero")
plus that slot; it reproduces the known HeroStateRunLocal descriptor 0x6022D40.
The getter bytes are validated at start-up; on mismatch nothing is ever hidden.
state_watch.py logs hero state names whenever they change (read-only) to find
which state a screen uses.

The overlay also hides unless the native current-map ID (RVA 0x51615C8 index into
the ID array via 0x51F1E90) equals a map we have art for (Sargasso 0xBD52B112).
In "MAP OFFLINE" areas that pointer chain is null, so current_map_key() returns
None. Sprint assist is not tied to this check and keeps working there.

## Multiple planets

maps.json maps the native map id (the fog/pause-map key from current_map_key()) to an
extracted texture and that map's exact MapMin/MapMax bounds, read from its fog record
(fogread.table(): record +0x20 min x/z floats, +0x48 max). select_map() loads the art
when the id changes; markers (minimap_icons.json) and pause-map scale
(map_scales.json) are stored per map id. Unknown ids hide the overlay.

Planet textures live under materialgraph/ui/Material_Textures/<name>_map_UV.texture:
sargasso_map_UV_6-17-2021, zurkies (Scarstu Debris Field), megalopolis, nef, savali,
zordoom, blizarIntact, blizar_destroyed. Sargasso is stored uncompressed; the others'
2048 HD streams are GDeflate (archive comp_type 2). ALERT needs a libdeflate.dll with
GDeflate for those, and the game's dstorage.dll returns E_NOTIMPL for its CPU codec,
so extract_tex.py falls back to the uncompressed 512x512 SD mip when the HD stream comes
back empty. For full 2048 art, put ALERT's libdeflate.dll (from the v0.4.0-overdrive
release zip, Overdrive/libdeflate.dll, SHA-256 fd20e8d6...0657ae) in src/ and run
extract_tex.py from src (ALERT loads it from the working directory). It is Git-ignored.

To add a planet: extract its texture, confirm the pairing (explored fog cells should
land on the texture's land pixels; Scarstu scored 0.47 vs 0.24 for the runner-up),
and add an entry with bounds from its fog record. Pairing by score alone was not
decisive for planets with little exploration, so only verified entries are listed.

Pause-map scale (canvas px per world unit) is measured, not assumed: icon offsets
from the player icon equal (icon world - player world) * S, so two map openings at
spots >= 8 units apart give S from any fixed icon (map_scale()); the last opening is
kept in map_scale_snaps.json so a helper restart does not lose it. Until measured, a
provisional S = 1.5655 * 1112 / map width is used (assumes the pause map draws every
2048 px texture at the same canvas size; exact for Sargasso, unverified elsewhere).
Markers keep their raw capture (player xz + canvas offset) and are recomputed when the
measured S arrives. Sargasso's 1.5655 is the default.

Zoom adapts to map size: minimap radius min(190, 30% of extent), fullscreen height
min(1050, 115% of extent). Sargasso is unchanged.

## Map artwork, coordinate system and markers

extract_tex.py uses the bundled ALERT/dat1lib to open the game's toc and
archives, assemble texture mip data into DDS, then decode PNG through Pillow.
Inspect its CLI before invoking it. ALERT's own licensing remains applicable.
The runtime needs the extracted PNGs, not ALERT or an extraction pass each launch.
Original extraction implementation cites https://github.com/Tkachov/ALERT.

The Sargasso texture is maps/sargasso_map_UV_6-17-2021.png (2048 square).
Exact world bounds (maps.json, from the fog record) are X [-192,920], Z [-728,384].
Pixel density is texture width / (x_max - x_min). Texture coordinates are
`u=(X-x_min)*ppu`, `v=(Z-z_min)*ppu`. Y is vertical height and is omitted.
Earlier screenshot correlation in fitmap.py/fitmap2.py was an approximation;
native MapMin/MapMax bounds supersede it. These old scripts can overwrite the
calibration JSON: do not run them merely to validate current tracking.

The renderer pads the texture by 1024 px, crops around live player X/Z, applies
exploration shading, resizes to the requested view, then composites game icons.
The player remains in the center; map art does not rotate. Heading rotates the
player artwork; its default art direction requires a -90 degree correction.
An optional facing_offset.json stores a small correction measured from the
native pause-map player icon. Heading 0 is valid, not “missing.”

Pause-map MapIconData records are 0xE8 bytes:

| Offset | Data |
| --- | --- |
| 0x00 | int32 type (player record type 2) |
| 0x04..0x83 | image URI string |
| 0x84, 0x85 | visible, completed |
| 0xC6 | edge-arrow flag |
| 0xC8, 0xCC | float arrow angle, icon rotation |
| 0xD8 | uint32 ID |
| 0xDC | two float canvas coordinates |

arr.icons decodes these records. Runtime locates the player's record using its
MapIconPlayer.texture URI and an empty preceding slot; the old MAP_BASE is only
a validated hint. **This is still a memory scan for UI records**, unlike native
player and sprint reads. It needs bounded allocation and retry pacing.

Capture happens once per opening of the native map, before the user pans/zooms.
The player's own canvas icon is the reference (not blindly canvas center).
`worldX=heroX+(iconX-playerIconX)/1.5655`; Z uses the analogous canvas Y formula.
The default UI canvas is 1920x1080. Visible unclamped markers become world-space
records in minimap_icons.json. Completed icons are omitted. Clamped objectives
provide direction only; do not turn them into precise positions. Markers in the
captured viewport replace older entries; matching types within three units merge.
Collection updates may remain stale until the next native map opening.

## Fog and explored area

fogread.py reproduces the pause-map fog builder, identified from
GUI2::PauseMenuElementMapPage::InitMapTextures (RVA 0x1A55850).
Global table RVA 0x580FC08: keys pointer +0, records pointer +8, capacity +0x14,
record stride +0x20. Record: width +0x78, height +0x7C, buffer pointer +0x80.
If the signed pointer is negative, resolve it relative to record+0x80; otherwise
use it as absolute. Cell (row,column) is bit row*width+column, little-endian bits.

Current map key is resolved through RVA 0x51615C8 and the ID array reached via
0x51F1E90. Sargasso fog key is 0xBD52B112. The overlay reads the game's grid once
per second, including exploration from before the helper started. It resizes
the grid into padded texture space and composites explored land in lavender.
This replaces the older locally painted exploration trail. Fog exceptions
currently retain the last good mask; the native player reader intentionally
does not retain a stale position.

## UI and performance

overlay.py uses a topmost borderless Tk window, transparent color #010203,
70% opacity, and layered/transparent/toolwindow/noactivate extended styles.
The window covers the desktop but drawing is small except in fullscreen mode.
Tk/Pillow operations belong on the main thread. The keyboard toggle now uses
RegisterHotKey while the game is foreground, with a polling fallback if registration
fails. It has no Python callback in the global keyboard input path. The former
low-level hook could contend for the GIL and delay input during expensive work.

Fullscreen toggle latency (2026-10-07): opening used to take ~350 ms because every
frame re-applied the fog style to the whole view at 5120x1440. Now the fog style is
applied once to the padded texture in a worker thread whenever the native fog grid
changes (~0.6 s, off the Tk thread), then pre-scaled to the two fixed zooms. A frame
is a crop plus icons: ~10 ms fullscreen, ~2 ms minimap. Fullscreen renders only the
map's own rectangle and fills the rest with a flat canvas rectangle. The hotkey
thread wakes on QS_HOTKEY (MsgWaitForMultipleObjects) and overlay.run's `wake`
event redraws within ~5 ms; the 1 s fog refresh runs after drawing. Measured live
with --debug ("toggle -> full drawn in N ms"): 15-42 ms.

2026-10-07: the user reported severe input lag and computer slowdown during
sprint development. The running 2 ms polling helper was stopped. Accumulated
CPU time alone does not identify the cause. At that point no analysis Python
job remained running. A post-stop two-second sample showed the game at roughly
6.6 logical cores of CPU use; no overlay was then running. Do not attribute the
whole slowdown to the helper without an A/B measurement.

Potential contributors to check: excessive native sampling plus GIL contention
with the keyboard hook; repeated whole-region map-icon scans when no record is
found; fullscreen image compositing; duplicate overlay instances. The newer
persistent sprint-toggle reader no longer needs to chase one-frame animation
flags. Measure a bounded reader benchmark and total-process CPU before relaunch.
Do not leave multiple diagnostics or repeated multi-gigabyte scans running.

## Validation and next work

2026-10-07 (Claude): 42 isolated tests pass. The obsolete CancelGate was
removed and the fire-while-sprinting lock fix ("unstick") added. The two-mode sprint assist was verified live: walk, double jump,
Phantom Dash, aim, fire and Normal mode, both in-process and through a running
minimap.py. Results and probe tooling are in SPRINT.md. Helper CPU was about
0.2 of one core; SprintReader.sample() costs about 0.05 ms. Native reads poll
at 12 ms. Icon discovery uses 1 MiB chunks with URI overlap and a short yield,
plus 30-second retries after failure.

Still unverified: owner feedback on long play sessions and the earlier input-lag
report with the RegisterHotKey toggle, controller input, other planets' art, and
traversal states with no run component (expected to leave the assist idle).
Do not claim a mocked test proves that Windows input was accepted by the game.
Record measured outcomes and unresolved failures here as work continues.

When restarting, inspect the exact process command line and kill only the
minimap.py process. Start Python in this project cwd with a hidden window and
separate stdout/stderr logs. The minimap and assist share one lifecycle; do not
launch a second independent sprint worker.

To support another game build, rederive the native paths and update fingerprints
and tests together. To support other planets, extract their texture and exact
bounds, select by native map ID, and separate marker caches by planet. Current
Sargasso art/marker assumptions are not a general multi-planet implementation.
