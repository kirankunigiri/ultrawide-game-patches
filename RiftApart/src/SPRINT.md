# Sprint assistance - native toggle state

## Behavior and controls

Starts and stops with minimap.py. **Always sprint is the default** when no valid
sprint_settings.json exists. F8 switches to Normal sprint and persists the choice.
Both modes cancel while left mouse (fire) or right mouse (aim) is held.

Always sprint enables sprint after 150 ms of valid native sprint-off state while
WASD movement is held and neither mouse button is held. This waits for a run
component after jump/dash instead of assuming a jump key always ended sprint.
Normal sprint never enables sprint automatically.

Requires the game's **toggle sprint** setting, **Left Shift**, WASD movement,
left-mouse fire and right-mouse aim. It emits an 80 ms scan-code Shift pulse
using SendInput, then releases it. The game performs its normal transition.
Mouse input passes through untouched. In live tests fire and aim started on the
same frame as the button press; the cancel follows within one poll. In Always
mode a manual Shift press to stop sprinting is undone after 150 ms while you
keep moving; switch to Normal (F8) if you want manual control. Controller and
remapped controls are not implemented.

Use --debug on minimap.py for diagnostics; default runtime is silent.
F8 mode is also shown in the fullscreen map caption, not beneath the small map.

## Why earlier versions missed

The first reader used HeroStateRun +0x147. RVA 0x7DB381 compares the current
animation locomotion hash with 0x4657204C (kSpeedSprint) and writes this boolean.
Callbacks 0x7DAB40 / 0x7DABB0 then emit HeroSprintStartEvent /
HeroSprintStopEvent. These are downstream notifications, not proven commands
that clear the user's toggle.

In a user-reproduced miss, the flag turned off on fire-down and pulsed on for
roughly one frame while movement and fire remained held. The user confirmed
the character kept sprinting. A 25 ms confirmation requirement rejected those
brief readings. Removing that filter and polling at 2 ms did not address the
underlying semantic mistake and added unnecessary polling load.

## Traced input toggle (build 3.630.1.0)

Addresses below are RVAs; add the loaded executable base.

| Item | RVA or object offset |
| --- | --- |
| HeroStateRunLocal descriptor | 0x6022D40 |
| Descriptor getter | 0x7DC590 |
| Sprint-input update | 0x7DEAF0, vtable +0x100 |
| Actual local toggle boolean | component +0x1CF |
| Pointer cache used by input routine | component +0x108 |
| Sprint mode setter called by input routine | 0x6C68B0 |
| HeroMacroState descriptor | 0x60052C0 |
| Macro-state query | 0x193F6E0, tests DWORD +0x4C |
| kSprint macro mask | 0x20000000, bit 29 |

The decisive branch at 0x7DEC9B checks byte +0x1CF. It clears the byte and passes
EDX=0 when on, or sets it to 1 and passes EDX=1 when off, then calls 0x6C68B0.
The surrounding routine reads HeroButtonCache action 0x83646CE7. Another branch
uses action 0x015D609F and supports its hold/toggle setting. Those action IDs
should not be relabeled from guesswork; the important evidence is the shared
toggle and call to the sprint mode setter.

0x6C68B0 compares/stores its mode at +0xA8 and updates weapon state and the
HeroMacroState kSprint bit. Setting this field directly would bypass associated
side effects; the helper does not write it. Virtual +0x110 (0x7DEE00) is called
as a native eligibility check by the input routine; we do not invoke it remotely.
The game continues to enforce its own movement/weapon eligibility when receiving
the ordinary Shift input.

The code signatures in sprint_assist.py validate the descriptor getter,
toggle branch and component lookup. The reader resolves the native hero via
player_tracking.HeroReader, looks up the active local-run component in the
entity table, checks its owner (+0x10), its sprint-update vtable entry and a
0/1 toggle value, then rechecks hero identity, table header, entry, component
header and flag. A missing component is unknown, not false. Relaxed idle, jump,
dash and other states can temporarily have no local-run component.

No heap scan, guessed velocity, remembered Shift parity, remote function call
or game-memory write is used for player or sprint state.

## The fire-while-sprinting lock (why cancellation alone missed ~50%)

Native game bug: fire while sprint is on and the game clears +0x1CF and the
mode (+0xA8) itself on the fire frame, but keeps a latent "resume sprint" and
re-enters the plain run state every other frame. The hero then alternates
HeroStateRunLocal / HeroStateStrafeLocal and the weapon barely fires, until a
direction change or a Shift press clears the latent sprint (1-3 s for the
owner). Without the assist this happened on every fire-while-sprinting press.

The old policy only cancelled when it saw toggle=1 with a mouse button held.
The click reaches the game before our Shift, so whenever the game handled the
click first the helper read 0, did nothing, and the lock occurred. That race
was the owner's 50%. Writing memory from Python would not win the race either:
the game acts on the click in the same frame.

Fix ("unstick"): a Shift pulse during the lock clears the latent sprint, and
the game then enters Strafe/Firing steadily (verified). SprintGate sends it when:

1. the press began while the last reading was sprinting, and the toggle now
   reads off without our cancel (the game took the click first): immediately;
2. fallback: the plain run class (RTTI `.?AVHeroStateRunLocal@Hero@@`) is seen
   3 times while fire/aim is held, at least 30 ms after the press.

If the pulse is skipped because the pre-send re-check raced a state change, the
gate restores its armed state (not_sent) so the next 12 ms poll acts again instead
of falling back to the slower run-sighting signal (owner still saw rare locks).

With --debug, the worker keeps ~3 s of decisions and appends them to
research/sprint_lock.log whenever a lock (plain run state returning while fire/aim
is held) lasts over 0.25 s. Rows: time, allowed, status, (toggle, plain-run),
combat, moving, shift, armed, action (sent or skipped with the reason).

Walking (not sprinting) and firing never triggers it: that press is not armed
and the run state does not return. After an unstick, Always mode re-enables
sprint ~150 ms after release; Normal mode leaves it off.

## Hover boots (auto hover)

Once the hero has hover boots, Shift is hover (speed mode). Measured live
(2026-10-09): hover lasts only while Shift is held, plus ~0.2 s after release, then
the hero drops to plain run with the sprint toggle still on. A tap (the old 80 ms
enable pulse) therefore gave a ~0.2 s hover that "turned off instantly". Hover runs
in HeroStateHoverbootLocal, a RunLocal subclass found through the same descriptor
and sharing the sprint input routine and +0x1CF toggle.

The gate learns hover boots the first time it sees HeroStateHoverbootLocal and saves
`"hover_boots": true` in sprint_settings.json. From then on, Always mode makes Shift a
hover toggle (HoverToggle) and never auto-starts hover or sprint:

- The user's own Shift press flips hover on/off. Physical presses are told apart from
  ours with Raw Input (RawShift: RIDEV_INPUTSINK on a message-only window; SendInput
  arrives with hDevice 0 - verified, our taps produced no events). This is not in the
  system input path, unlike the removed low-level hook.
- While on, the helper keeps Shift held. A physical release also releases the key for
  the game, so the helper presses it again at once (measured: hover survives a 30 ms
  release; hover follows the held key, not the +0x1CF toggle).
- Aim (right mouse) releases Shift; hover resumes when aiming stops. The fire-lock
  unstick tap still runs, 40 ms after the release so the game sees a separate press.
- Left click is the hover boost (three clicks speed up) and is ignored while hover is on.
- Menus, map, cutscenes and focus loss turn hover off. Normal mode (F8) leaves Shift
  entirely to the game (hold to hover).

An earlier version held Shift automatically whenever WASD was held (auto hover); the
owner preferred manual on/off.

Grinding and other non-run states are never sent an enable (KINDS/ENABLE_KINDS).

## Policy, race checks and lifetime

SprintGate returns cancel, unstick, enable or no action. It samples native state
every 12 ms while the game is eligible; inactive polling sleeps 50 ms. Actual
interval includes processing and Windows scheduling. A known-on toggle plus
fire/aim requests cancellation. A known-off toggle never requests cancellation.
Enable requires Always mode, movement, no combat and a 150 ms off interval.
Unknown state, focus loss and identity changes reset that interval.

Pulses have a 300 ms cancellation retry delay and 600 ms enable retry delay.
If the game ignores a pulse, a later fresh mismatch can retry. A cancel may
preempt the enable cooldown, so firing immediately after auto-enable is not
held up for 600 ms. Physical Shift or the helper's active pulse blocks another
press. Immediately before sending, the worker re-reads native state and checks
focus, overlay heartbeat, mouse intent and movement again. It never queues a
stale cached-state toggle for later.

The worker releases its key after 80 ms, promptly on focus loss, and in its
finally block on orderly shutdown. Force-killing Python bypasses finally; do
not kill it during an active injected press. No game instance is terminated.

## Tests and verification status

test_sprint_assist.py uses fake memory to exercise descriptor hash collisions,
ownership, invalid layouts, short reads, identity races, and animation-off with
toggle-on. Policy tests cover both modes, combat release, jump/dash component
gaps, physical Shift, idle/unknown/menu guards, retry timing and persistence.
The old cancellation-only CancelGate and its tests were removed; SprintGate
covers both modes.

### Live verification (2026-10-07, build 3.630.1.0, keyboard + mouse)

Driven by state_probe.py with injected WASD/Space/Ctrl/mouse input. Every run
returned the hero to its start point (closed-loop walk back).

| Scenario | Native observation | Assist result |
| --- | --- | --- |
| Walk forward, Always | RunLocal toggle 0 | Shift sent ~160 ms later, toggle 1 |
| Double jump while sprinting | Jump/Fall have no run component; JumpLand reports toggle 0 | Re-enabled ~170 ms after landing |
| Phantom Dash (Left Ctrl) | PhaseDodge has no run component; Run returns with toggle 0 | Re-enabled ~170 ms after dash |
| Fire while sprinting, no assist | Lock: Run/Strafe alternate for the whole hold | (baseline bug, 2/2) |
| Fire while sprinting, old policy | Owner capture: 3 locks of 1-3 s | Nothing sent (toggle already 0) |
| Fire while sprinting, unstick fix | Steady Strafe + Firing 15-32 ms after click | 5/5 unstuck at once; earlier 3-sighting version 2/2 at ~110 ms |
| Aim (RMB) while sprinting | Cancel path; steady Strafe ~45 ms after click | Re-enabled ~150 ms after release (3/3) |
| Walk and fire, Normal, not sprinting | Strafe, no lock | No Shift sent (2/2) |
| Normal mode, manual sprint + aim | Toggle 1, then 0 | Cancel only; never re-enabled |

Jump and dash really do clear the native toggle (the game restarts the run
state with +0x1CF = 0), so the 150 ms off-interval plus WASD check is the right
trigger. JumpLand/Strafe are RunLocal subclasses found through the same
descriptor and pass the vtable check. Right after a Shift during fire/aim the
toggle can read 1 for one sample (~15 ms); the 300 ms retry absorbs it.

Measured cost: SprintReader.sample() is about 0.05 ms; the whole helper
(overlay + assist) used about 0.2 of one core with the game focused.

Not covered live: controller input, remapped keys, hoverboots, grind rails,
swimming, cutscenes, weapons other than the one equipped during tests, and
long play sessions.

### Live probe tools

- comp_dump.py: lists the hero's components with RTTI names (read-only).
- state_probe.py: drives an input script and logs HeroState components, the
  native toggle and distance from start every 10 ms. Events: `+w`/`-w` key
  down/up, `^space` tap, `+rmb`/`-lmb` mouse, a number sleeps, `home:s` walks
  back to the start with S. `ASSIST=always|normal` runs SprintAssist in-process;
  without it, observe a separately running minimap.py. `PROBE_LIMIT` (default 12)
  releases every key when the hero gets that far from the start.
  Example: `ASSIST=always python state_probe.py +w 0.4 ^ctrl 0.8 -w home:s`.
  Only run it in a flat, safe area: it moves the character. It writes
  state_probe_log.json; `python fire_trials.py [lmb|rmb]` summarizes the hold.
- glitch_log.py: passive capture while the owner plays (`python glitch_log.py
  300 always`), sending nothing beyond its in-process assist. Stop minimap.py
  first so only one assist runs. `python glitch_analyze.py [detail]` lists
  each LMB hold and when firing became steady.
