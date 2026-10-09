# Native hero tracking fix

The project remains in this directory; launch it here with `python minimap.py`.
The reader supports the inspected RiftApart.exe 3.630.1.0 and verifies the relevant
machine-code instructions before trusting the layout.

## Reproduced failure

The previous `heroread.hero_xz()` voted over every scanned pointer chain. After a
section transition, many chains resolved to the SAME recycled scratch buffer.
Finite zero/subnormal floats were accepted and those aliases outvoted the real
hero. At the reported failure, it returned approximately (0, 0), while the native
hero transform was (120.402466, 8.05, -306.721283). Its filter also retained an old
position indefinitely if all reads failed. More scanning or a larger majority
would not establish which object was the player.

## Verified native code path (RVAs, add the loaded executable base)

The pause-map routine at RVA `0x5EC8D0` reads the hero this way:

1. `0x5EC8E9`: LEA RCX, [exe + 0x6003E88], the hero entity handle.
2. `0x5EC90A`: CALL `0xF1A520`, the entity-handle resolver.
3. `0x5EC917`: CALL `0x29F7C0`, the entity position getter.
4. `0x5EC91C` onwards copies X/Y and Z, then discards Y for the 2D map.

The resolver extracts index = handle & 0xFFFFF and generation =
(handle >> 20) & 0x7FF. Generation zero is invalid. It obtains the entity pool
pointer at exe+0x6748978 and count at exe+0x6748994. Entries are 0xC0 bytes;
the entry's uint16 generation at +8 must match the handle, and index < count.

The getter reads the transform pointer at entry+0 and returns transform+0x30.
Its null-transform branch returns a thread-local fallback; the overlay instead
reports tracking unavailable. XYZ occupies matrix row 3; the character's forward
axis is row 2, so heading = atan2(matrix[10], matrix[8]). This axis was also
validated against movement in Claude's earlier root-transform experiments.

`player_tracking.HeroReader` reproduces those memory reads outside the game. It
does NOT invoke internal functions, inject code, write game memory, or perform
heap scans for player positions. It re-resolves the current entity every sample,
checks its generation, validates the matrix, and rechecks the handle, allocation,
and transform pointer after the read. It retries once on a race, then reports
unavailable. No candidate consensus, persistent heap addresses, or stale fallback
is used. Real teleports and replacement player objects take effect immediately.
Position and heading used by the overlay come from one sample.

Directly executing the getter would require arranging execution in the game's
process with its object/thread context. This getter simply returns a pointer, so
reproducing its reads achieves the useful result without a remote call.

## Files

- `player_tracking.py`: process-independent native reader and executable signatures.
- `heroread.py`: Windows/process adapter; keeps hero_xz(), hero_xz_filtered(), and
  hero_heading() for existing callers. The filtered name is now a compatibility alias.
- `minimap.py`: consumes one native sample per frame and displays a waiting status
  instead of a false position when tracking is unavailable. Removed obsolete player
  scan/reacquire code and fixed heading 0 being treated as missing by the renderer.
- `test_player_tracking.py`: isolated regression tests, runnable with
  `python -m unittest test_player_tracking -v`, without launching the game.

## Validation

15 tests pass: live-style coordinates/heading, duplicate stale aliases, player
replacement, pool relocation, generation mismatch, missing transform after a good
sample, null handle, index bounds, NaN/zero/malformed matrices, legitimate origin,
teleports, short reads, executable mismatch, and two mid-read identity races.
Python compilation passed. A 600-sample, 30-second live idle check had zero missing
reads; mean read time was 0.124 ms, maximum 0.577 ms. The restarted overlay was
visually confirmed to center on the currently occupied island.

The previous experimental scripts (`chaincheck.py`, `rootcheck.py`, `jumpdiag.py`,
`bench.py`, UI tests) were reviewed. They rely on scanned copies/old reader internals
and/or send movement input. Their scan-based agreement is not an authoritative
regression oracle. Tests above specifically exercise the reported failure and
entity lifetime changes. A real section transition and game restart are still
unverified in the live session.

## Marker cache and remaining scope

The old marker cache contained Z positions beyond Sargasso's maximum of 384,
consistent with captures made using a wrong player location. It is preserved as
`minimap_icons.before_native_tracking.json`; the active cache was reset. Open the
normal pause map once to refresh the markers at the correct coordinates.

The background art remains Sargasso-specific. Marker acquisition still uses the
existing pause-map icon array and refreshes on map opening. This change fixes
player identity/location; it does not add maps for other planets or replace the
existing marker acquisition mechanism. A game update that changes verified code
will disable tracking with an unsupported-code status rather than use guesses.
