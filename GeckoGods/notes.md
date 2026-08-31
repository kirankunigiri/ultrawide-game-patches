# Gecko Gods - Ultrawide Patch Notes

Full technical write-up for making **Gecko Gods** (Inresin) behave correctly at
**5120x1440 / 32:9**: correct camera framing, correct menu/UI scaling, and the window
actually running at the ultrawide resolution.

The fix is a **MelonLoader mod** (`GeckoUltrawide.dll`) - no game files are modified.

---

## 1. The game

| | |
|---|---|
| Engine | Unity **6000.0.65f1** (Unity 6) |
| Scripting backend | **IL2CPP** (`GameAssembly.dll`) |
| Render pipeline | **Built-in** (probe reported `SRP=False`) |
| Camera | `MAIN_CAMERA`, perspective, base fov **60**, uses **Cinemachine** |
| Company / Product | `Inresin` / `Gecko Gods` (used by `MelonGame` attribute + registry path) |
| Settings registry | `HKCU\Software\Inresin\Gecko Gods` |

This is a completely different situation from the other games in this repo:

| Game | Engine | Approach |
|---|---|---|
| Bastion | Custom C# / FNA, unobfuscated | Hand-patch the IL with Mono.Cecil |
| Hades | Native C++ (The Forge) + Lua | Community tool (Hephaistos) |
| **Gecko Gods** | **Unity 6, IL2CPP** | **Runtime mod (MelonLoader)** |

IL2CPP compiles the C# to native machine code, so there is no managed assembly to edit like
Bastion. The game's own types are also **name-obfuscated** (e.g. `MCJPDNBMJCJ`), so there is
nothing useful to hook by name. The practical approach is therefore to let the game run and
**correct Unity's own objects at runtime** (`Camera`, `CanvasScaler`, `Screen`).

---

## 2. The problem

At 32:9 the game's framing and menus were wrong - content that belongs at the top/bottom was
cut off while things spread out to the sides.

Root cause is Unity's default camera behaviour. `Camera.fieldOfView` is the **vertical** fov,
and Unity holds it **constant** as the window gets wider. At 16:9 the game's fov of 60
vertical corresponds to about **91.5 degrees horizontal**. At 5120x1440 (aspect 3.556) that
same 60 vertical balloons to roughly **128 degrees horizontal** - a very wide, distorted
view that does not match how the game is composed.

---

## 3. The fix

Three things, all applied at runtime from `OnLateUpdate`:

### 3.1 Force the resolution
The game was launching at **2560x1440 windowed** (16:9) - so it was not even rendering at
32:9. The mod calls `Screen.SetResolution(5120, 1440, FullScreenMode.FullScreenWindow)` about
2 seconds after a scene loads (once per scene, and only if it does not already match).

Configurable: `ForceResolution`, `ForceWidth`, `ForceHeight`, `ForceBorderless`.

### 3.2 Camera FOV
Each frame, `Camera.main`'s vertical fov is replaced with the vertical fov whose **horizontal**
fov equals the game's horizontal fov at 16:9:

```
vfov' = 2 * atan( tan(vfov/2) * (baseAspect / screenAspect) )
```

With `baseAspect = 16/9`, at 5120x1440 this measured **60.00 -> 32.20** in game. This keeps
the game's intended 16:9 horizontal framing while filling the wider screen, instead of letting
Unity stretch the view to ~128 degrees horizontal.

> **Naming note:** the helper is called `MatchedVerticalFov`. An earlier draft called this
> `ToHorPlus`, which was inaccurate - the formula holds the **horizontal** fov constant, it is
> not the textbook Hor+ transform. The behaviour below is what was tested and confirmed good
> in-game; only the name/comment were corrected. If you ever want true Hor+ (constant vertical
> fov, more world revealed horizontally) that is simply Unity's *stock* behaviour - disable
> `FixCameraFov`.

**The game re-sets fov to 60 every frame** (Cinemachine drives it), which the log confirms:

```
[FOV] MAIN_CAMERA 60.00 -> 32.20 (aspect 3.556)
[FOV] game re-set fov to 60.00 (we set 32.20) - game drives fov each frame, re-applying
```

This is why the fix runs in `OnLateUpdate` (after Unity's `LateUpdate`, where Cinemachine's
brain updates) and re-applies continuously rather than once.

### 3.3 UI / CanvasScaler
All `ScaleWithScreenSize` scalers are forced to `MatchWidthOrHeight = 1.0` (**match height**)
so menus keep their vertical framing and expand sideways.

In practice the probe showed this game's scalers were **already** match-height, so this is
effectively a no-op safety net here - kept because it costs nothing and protects against
scalers created later:

```
scaler Slot Menu         mode=ScaleWithScreenSize ref=(1600x900)  match=MatchWidthOrHeight/1.00
scaler Canvas - Main Menu mode=ScaleWithScreenSize ref=(1600x900)  match=MatchWidthOrHeight/1.00
scaler Canvas            mode=ConstantPixelSize   ref=(800x600)   match=MatchWidthOrHeight/0.00
scaler DebugHUD          mode=ScaleWithScreenSize ref=(800x600)   match=MatchWidthOrHeight/1.00
scaler [Graphy]          mode=ScaleWithScreenSize ref=(1920x1080) match=MatchWidthOrHeight/1.00
```

---

## 4. IMPORTANT: the IL2CPP crash lesson

**v0.1 hard-crashed the game instantly** (no error, no stack trace, log just stopped mid-probe).

Cause: **`Camera.allCameras` does not exist** in this game's generated IL2CPP interop assembly.
Calling a missing IL2CPP member is a **native crash** - a C# `try/catch` cannot catch it, and
nothing is written to the log.

Two rules that came out of this, both baked into the mod:

1. **Verify every API exists** in `MelonLoader\Il2CppAssemblies\*.dll` before calling it.
   Confirmed-present and safe here: `Camera.main`, `Camera.allCamerasCount`,
   `Camera.GetAllCameras(Il2CppReferenceArray)`, and the **non-generic**
   `Object.FindObjectsOfType(Type)` used with `Il2CppType.Of<T>()`.
   Absent: `Camera.allCameras`.
2. **Breadcrumb before every risky call.** `BC("...")` logs *before* the call, so a native
   crash leaves the culprit's name as the final log line. This is the only reliable way to
   debug native crashes, and it is what located this one on the first try.

The riskier full-camera enumeration is behind an opt-in preference (`EnumerateAllCameras`,
default `false`).

---

## 5. Building

Needs the **.NET 8 SDK**, MelonLoader installed into the game, and the game launched **once**
so `MelonLoader\Il2CppAssemblies\` exists.

```powershell
# from GeckoGods/src
dotnet build -c Release
# or point at a different install:
dotnet build -c Release -p:GameDir="D:\Games\Gecko Gods"
```

Output: `bin\Release\net6.0\GeckoUltrawide.dll` -> copy into `<game>\Mods\`.

---

## 6. Configuration

After the first run, edit `<game>\MelonLoader\UserData\MelonPreferences.cfg`, section
`[GeckoUltrawide]`:

| Key | Default | Meaning |
|---|---|---|
| `Enabled` | `true` | Master switch for the fixes (probe still logs) |
| `FixCameraFov` | `true` | Apply the fov correction |
| `FixHudScaling` | `true` | Force CanvasScalers to match-height |
| `EnumerateAllCameras` | `false` | Opt-in riskier camera enumeration in the probe |
| `ForceResolution` | `true` | Force the window to the target resolution |
| `ForceWidth` / `ForceHeight` | `5120` / `1440` | Target resolution |
| `ForceBorderless` | `true` | Borderless fullscreen vs windowed |
| `BaseAspect` | `1.7778` | The game's design aspect (16:9) - leave alone |

**Other resolutions:** set `ForceWidth`/`ForceHeight`. The fov math derives from the live
screen aspect, so nothing else needs changing (e.g. 3440x1440 works as-is).

---

## 7. Uninstall / troubleshooting

- **Disable the mod:** delete `<game>\Mods\GeckoUltrawide.dll`, or set `Enabled = false`.
- **Remove MelonLoader entirely:** delete `version.dll`, `dobby.dll`, the `MelonLoader\` folder
  and `Mods\` from the game directory.
- **Game crashes instantly, log ends abruptly:** that is a native IL2CPP crash. Read the last
  `[bc]` breadcrumb in `MelonLoader\Latest.log` - it names the call that died.
- **Game updates** may regenerate `Il2CppAssemblies`; MelonLoader handles this automatically on
  next launch. The mod itself is version-tolerant (it only touches Unity APIs, not game code).

---

## 8. Discovery method (reusable for other Unity IL2CPP games)

1. Identify the backend: `<Game>_Data\il2cpp_data` present = IL2CPP; `Managed\Assembly-CSharp.dll`
   = Mono (much easier - patch it directly like Bastion).
2. Read `<Game>_Data\app.info` for Company/Product (needed for `MelonGame` and the registry path).
3. Read the Unity version from `UnityPlayer.dll` strings.
4. Install MelonLoader, launch once to generate `Il2CppAssemblies`.
5. Inspect those assemblies to confirm which APIs actually exist before calling them.
6. Write a **diagnostic-first** mod: probe and log the real camera/UI state, with breadcrumbs.
   Do not guess - obfuscated game code means the engine objects are the reliable surface.
