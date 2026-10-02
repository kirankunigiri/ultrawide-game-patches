# Fatal Claw - Ultrawide Patch Notes

Full technical write-up for making **Fatal Claw** render correctly at **5120x1440 / 32:9**
(and 21:9 through the config): full-width image, correct field of view, cutscenes, the
gate-teleport zoom and the camera tint overlay.

The fix is a **UE4SS Lua mod** (`UltrawideFix`). No game files are modified.

The mod is a plain Lua script, so `dist/UltrawideFix/` is both its source and the drop-in.
`src/package.ps1` builds the one-zip release (UE4SS + settings + the mod) that's published
on the repo's GitHub Releases page.

---

## 1. The game

| | |
|---|---|
| Engine | Unreal Engine **4.27** (`++UE4+Release-4.27` in the exe), Windows build dated 2026-08-26 |
| Look | 2.5D: Paper2D sprites and Spine-animated characters filmed by a perspective camera |
| Gameplay camera | `BP_FCHeroCamera`: CameraComponent with FOV **60** (horizontal), `bConstrainAspectRatio = true`, plus a darkening sprite (`LayerSpriteComponent`) 200 units in front of the lens |
| Title camera | `BP_TitleCamera` (level instance `Title_StainedGlass`), FOV **90**, set every frame |
| Cutscenes | Level Sequences (e.g. `LS_Teleport_Go_To` / `LS_Teleport_Come_From`) that drive `SetFieldOfView`; one pre-rendered movie (`Movie_Opening_SancSymbolChange.webm`, 1920x1080) |
| Aspect handling | `LocalPlayer.AspectRatioAxisConstraint = MaintainXFOV` |
| Content | One 3.6 GB pak with an **encrypted index**, so assets can't be browsed offline |

How it compares to the other games in this repo:

| Game | Engine | Approach |
|---|---|---|
| Bastion | Custom C# / FNA, unobfuscated | Hand-patch the IL with Mono.Cecil |
| Hades | Native C++ (The Forge) + Lua | Community tool (Hephaistos) |
| Gecko Gods | Unity 6, IL2CPP | Runtime mod (MelonLoader) |
| **Fatal Claw** | **Unreal Engine 4.27, encrypted pak** | **Runtime mod (UE4SS Lua)** |

The game logic is cooked Blueprint and the pak index is encrypted, so there is nothing
practical to patch on disk. UE4SS injects a Lua runtime that can read and write any
reflected property and hook any reflected function, so the fix corrects the engine's own
camera objects while the game runs.

---

## 2. The problem

At 32:9 the game draws a 16:9 picture with black bars on both sides. That is not a config
setting: the game's cameras set `bConstrainAspectRatio = true`, which makes UE pillarbox
the view to the camera's 16:9 aspect. Editing `Engine.ini` does not help either. The game
rewrites that file on exit, and the lock is a per-camera property anyway.

Removing the lock alone is not enough. In UE (with `MaintainXFOV`) `FieldOfView` is the
**horizontal** field of view, so a 60 degree camera stretched over a screen twice as wide
still shows the same width of the world. The picture looks about 2x zoomed in, with the
top and bottom of the scene cut off.

---

## 3. The fix

Everything happens at runtime, from a post-hook on `CameraComponent:SetFieldOfView` plus a
250 ms loop that runs on the game thread.

### 3.1 Remove the 16:9 lock
`bConstrainAspectRatio` is cleared on every camera. The loop re-checks every 250 ms, so
cameras created later (level loads, cutscenes) are covered too.

### 3.2 Hor+ field of view
Every camera FOV is widened so the **vertical** view stays exactly what it is at 16:9 and
the extra width reveals more of the world to the sides:

```
fov' = 2 * atan( tan(fov / 2) * (screenAspect / (16/9)) )
```

| Resolution | Aspect | Gameplay 60 | Title 90 | Gate zoom 40 | Tint overlay width |
|---|---|---|---|---|---|
| 5120x1440, 3840x1080 (32:9) | 3.556 | 98.2 | 126.9 | 72.1 | x2.000 |
| 3440x1440 (21:9) | 2.389 | 75.6 | 106.7 | 52.1 | x1.344 |
| 2560x1080 (21:9) | 2.370 | 75.2 | 106.3 | 51.8 | x1.333 |
| 3840x1600 (21:9) | 2.400 | 75.9 | 106.9 | 52.3 | x1.350 |

The LocalPlayer's `AspectRatioAxisConstraint` is pinned to `MaintainXFOV` (the game already
uses it) so the formula always matches what UE does. `FovScale` in the config multiplies
the result for people who want a different zoom.

### 3.3 Per-frame FOV: cutscenes, title intro, gate zoom
The title intro, the in-engine cutscenes and the gate-teleport zoom set the FOV **every
frame** through `SetFieldOfView`. Converting once is useless because the next frame
overwrites it, so a post-hook on `/Script/Engine.CameraComponent:SetFieldOfView` converts
each call right after the game makes it. The gate entry, from a per-call trace: raw 60 for
a moment, 60 -> 40, a short hold, then 40 -> 11 into the portal, about 200 calls a second;
converted that is 98.2 -> 72.1 -> 21.8. The exit plays the zoom back out.

A Blueprint SET node writes the property directly and never goes through the setter, so
the 250 ms loop also converts any camera whose FOV is not a value the mod wrote. In
practice every FOV change in this game goes through the setter.

### 3.4 Never converting a value twice
If the game reads back a converted FOV and sets it again (a cutscene restoring the FOV it
captured when it started, for example), converting it again would zoom out further each
time. The mod recognises its own values by **exact float match** against:

- the last 8 values it wrote to that camera, and
- up to 16 "resting" values per camera: values of ours that were still in place at a loop
  tick, which is what a cutscene captures as its starting state.

Anything else is a new raw value and gets converted. Both lists are fixed-size, so nothing
grows with play time or with the number of teleports. Section 4 explains why the match has
to be exact.

### 3.5 Camera tint overlay
`BP_FCHeroCamera` carries a Paper2D sprite (`LayerSpriteComponent`, relative location
(200, 0, 0), yaw 90, scale (0.2, 1, 0.2)): a darkening overlay sized for the 16:9 view. At
32:9 the visible width doubles, so the overlay only covered the middle and left a lighter
band at each edge. Sprites attached to a camera are found the first time the camera is
seen (and checked again 2 s later in case the Blueprint attaches them late), then widened
along whichever local axis faces sideways after their rotation (local X here): 0.2 -> 0.4
at 32:9. The factor is the real visible-width ratio `tan(fov'/2) / tan(fov/2)`, which is
screenAspect / (16/9) at `FovScale` 1.

### 3.6 Deliberately left alone
- **Level Sequence spawnable templates** (objects inside sequence assets, names containing
  `:MovieScene`). Editing a template edits the asset itself.
- **The camera manager's `AnimCameraActor`**: a hidden camera that camera animations write
  raw FOV into. It drives animations; it is not a view.
- **SceneCaptureComponent2Ds** on the teleporters, `BP_HeroStoneWarpEnd`,
  `BP_HeroForUIAnim` and `BP_SpineHero`. They render **only the hero** (show-only list)
  into `RT_Hero` / `RT_Hero_Dash` at FOV 60 for warp effects. They are not screen
  snapshots: changing their FOV shrinks the hero in the effect, and disabling them hides
  the hero during warps.
- **Cine cameras**: the game has none. If one ever shows up, its sensor width is widened
  instead of its FOV, because cine cameras recompute FOV from the lens every tick.

---

## 4. The gate-teleport flicker (post-mortem)

**Symptom.** During a gate teleport, pieces of a zoomed-in version of the frame flickered
over the correct one. First gate: entry fine, exit flickered. Every gate after that: entry
and exit, worse each time. Normal (stone warp) teleports were fine.

**Cause: the mod's own "already converted?" check.** Earlier versions remembered **every**
FOV value they had ever written, **rounded to 0.01**, in one set shared by all cameras, and
skipped any incoming value found in it. The gate zoom sweeps the raw FOV through 11-60,
and the converted values from the previous zoom cover 21.8-98.2. On random frames a raw
value matched a remembered converted one (raw 40.28 against an earlier converted 40.28),
was skipped, and that single frame rendered at the raw, zoomed-in FOV. Single zoomed-in
frames mixed in with correct ones read as pieces of a zoomed-in frame fighting the right
one.

**Why it compounded.** Each zoom added about 700 values to the set, so the chance that a
raw frame collided kept rising. Replaying the traced entry curve backwards (as the exit)
through the old rule skipped 33 of about 900 frames. A simulation of 10 gate teleports
(zoom curves modelled on the trace, uneven frame rates) left 0 frames zoomed in on the
first entry (nothing remembered yet), 50 on the first exit, then 36, 110, 66, 120 and
climbing to 200-390 per zoom by the last teleports. It could not grow forever, since there
are only about 17,000 two-decimal values between 0 and 170, but at that point the whole
zoom would have played unconverted. The same simulation through the current rule (exact
match, small per-camera window, section 3.4) leaves 0 bad frames on all 20 zooms.

**Ruled out on the way** (useful if something similar shows up in another game):
- camera animations through the camera manager's `AnimCameraActor` (the game plays none);
- Blueprint overrides of `BlueprintUpdateCamera` / `BlueprintModifyCamera` (the camera
  manager and its only modifier are stock engine classes);
- the hero SceneCaptures (turning all of them off changed nothing in the gate);
- post-process blendables or a view-target switch during the gate (there are none).

**What found it:** a per-call trace of every `SetFieldOfView` value during the gate, which
showed the entry curve being converted correctly, then a replay of that curve through the
old matching rule. Sampling the camera 4 times a second never caught it, because a skipped
frame is internally consistent (the camera and the view both hold the raw value).

---

## 5. UE4SS lessons

- **Use the experimental build.** Stable v3.0.1 cannot identify this game's engine (its
  `EngineVersion` and `FText` scans fail, "PS scan timed out"). Experimental
  `v3.0.1-1152-ge3ba1016` with `[EngineVersionOverride] MajorVersion = 4, MinorVersion = 27`
  works.
- **Run your loop on the game thread.** `LoopAsync` + `ExecuteInGameThread` runs Lua on
  UE4SS's async thread while hooks run Lua on the game thread: one Lua state, two threads.
  With the gate zoom firing the FOV hook about 200 times a second, UE4SS eventually died
  with `Ref was not function` (the mod silently stopped, sometimes the game crashed).
  `LoopInGameThreadWithDelay` fixed it.
- **Never schedule work from inside a hook callback** (`ExecuteWithDelay`,
  `ExecuteInGameThread`): same crash. Hooks only read and write properties; anything else
  is queued for the loop.
- **Blueprint overrides:** a hook on the `/Script/Engine...` declaration doesn't see a
  Blueprint override (the call goes to the override in the BP class,
  `/Game/...BP_X_C:Function`). Hooking Blueprint event graphs (`ExecuteUbergraph_...`)
  crashed UE4SS.
- **Don't sample engine state from inside a hook at frame rate.** Reading the camera
  manager's view-target properties on every call crashed with an access violation.
- **Keep the bundled example mods off.** The fix was tested with all of them disabled.
- **The game rewrites `Engine.ini` on exit**, so ini tweaks don't stick (and the 16:9 lock
  is per camera anyway).

---

## 6. Configuration

`dist/UltrawideFix/Scripts/config.lua`:

| Key | Default | Meaning |
|---|---|---|
| `ScreenWidth` / `ScreenHeight` | `5120` / `1440` | Your resolution; sets the aspect ratio the fix targets |
| `FovScale` | `1.0` | Multiplies the converted FOV (0.5 - 2.0). 1.0 = the game's 16:9 vertical view |
| `Debug` | `false` | `true` writes what the mod does to `ue4ss\UE4SS.log` |

`config.lua` is loaded by path from the mod's own `Scripts` folder. If it is missing or has
a typo, the mod uses the defaults above. A screen that is not wider than 16:9 makes the
mod switch itself off. Only 32:9 has been tested in-game; 21:9 runs the same code with a
different aspect.

**Logging.** Following the repo convention, the mod is silent by default and writes
nothing unless `Debug = true`. UE4SS itself always writes its own `ue4ss\UE4SS.log`
(startup, signature scans, which mods it starts); that is outside the mod's control.

---

## 7. Install, uninstall, troubleshooting

See [dist/INSTALL.md](dist/INSTALL.md). In short: extract the release zip
(`FatalClaw-Ultrawide-v<version>.zip`) into the game folder and, for 21:9, set the
resolution in `config.lua`. The zip is built by `src/package.ps1`, which downloads the
pinned UE4SS build (`UE4SS_v3.0.1-1152-ge3ba1016.zip`, SHA-256 checked), sets the engine
version override to 4.27, turns UE4SS's bundled example mods off and adds `UltrawideFix`.
Bundling matters because UE4SS's "experimental-latest" is a rolling release: the tested
build disappears upstream when a newer one is published, but the release keeps it.
Uninstall by deleting `ue4ss\Mods\UltrawideFix` (or `dwmapi.dll` + `ue4ss\` to remove
UE4SS too).

To publish a new version: bump `-Version`, run `src/package.ps1`, then
`gh release create fatalclaw-v<version> src/out/FatalClaw-Ultrawide-v<version>.zip` and
update the link in `dist/INSTALL.md`.

With `Debug = true`, a healthy start looks like:

```
[UltrawideFix] UltrawideFix 1.0: screen 5120x1440 (aspect 3.5556, game designed for 1.7778), FOV scale 1.00 - settings from ...\Scripts\config.lua
[UltrawideFix] hooked /Script/Engine.CameraComponent:SetFieldOfView
[UltrawideFix] main loop: game thread
[UltrawideFix] FOV 90.00 -> 126.87 on ...BP_TitleCamera.CameraComponent
[UltrawideFix] FOV 60.00 -> 98.21 on ...BP_FCHeroCamera_C_....CameraComponent
[UltrawideFix] widened tint sprite ...LayerSpriteComponent: X 0.200 -> 0.400
```

---

## 8. Not covered

- **The opening movie** (`Movie_Opening_SancSymbolChange.webm`, 1920x1080) is a video, not
  a camera, so the mod doesn't touch it. How it plays at 32:9 hasn't been checked.
- **HUD and menus** are left as the game draws them.
- **21:9** has not been tested in-game (same code, different aspect).

---

## 9. Discovery method (reusable for other UE4 games)

1. Get the engine version from the exe (`++UE4+Release-4.27`).
2. Install UE4SS. If the stable build can't find the engine, use experimental and set
   `[EngineVersionOverride]`.
3. Find what makes the bars: `FindAllOf("CameraComponent")` and check
   `bConstrainAspectRatio` / `AspectRatio`.
4. Remember UE's FOV is horizontal under `MaintainXFOV`: removing the bars alone zooms in,
   so convert every FOV with the Hor+ formula.
5. Hook `SetFieldOfView` for anything that drives FOV per frame (cutscenes, title screens,
   zoom effects), and keep a game-thread loop as the fallback.
6. Debug visual glitches with per-call traces, not periodic samples, and test any
   bookkeeping offline against recorded values before shipping it.
