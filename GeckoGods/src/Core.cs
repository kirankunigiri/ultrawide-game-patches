using System;
using MelonLoader;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Rendering;
using Il2CppInterop.Runtime;

[assembly: MelonInfo(typeof(GeckoUltrawide.Core), "GeckoUltrawide", "0.2.0", "Claude")]
[assembly: MelonGame("Inresin", "Gecko Gods")]

namespace GeckoUltrawide
{
    // Gecko Gods ultrawide (32:9) fix - MelonLoader mod for Unity 6 / IL2CPP.
    //
    // What it does:
    //   1. Forces the game window to the target resolution (default 5120x1440 borderless).
    //   2. Rewrites Camera.main's vertical FOV every frame so the ultrawide view keeps the
    //      same HORIZONTAL framing the game has at 16:9 (see MatchedVerticalFov below).
    //   3. Normalizes UI CanvasScalers to match-height so menus keep their vertical framing.
    //   4. Logs a one-shot PROBE per scene describing the real camera/UI state.
    //
    // IMPORTANT - crash lesson (v0.1 -> v0.2):
    //   Camera.allCameras does NOT exist in this game's IL2CPP interop assembly. Calling it
    //   is a NATIVE crash, which try/catch cannot catch - the game just vanishes with no
    //   error in the log. Only use APIs verified present in MelonLoader/Il2CppAssemblies.
    //   Every risky call below is preceded by a BC() breadcrumb so that if it ever dies
    //   again, the last line in the log names the exact culprit.
    public class Core : MelonMod
    {
        private MelonPreferences_Category _cat;
        private MelonPreferences_Entry<bool> _enabled;
        private MelonPreferences_Entry<bool> _fixFov;
        private MelonPreferences_Entry<bool> _fixHud;
        private MelonPreferences_Entry<bool> _enumerateCameras; // riskier path, opt-in
        private MelonPreferences_Entry<bool> _forceRes;
        private MelonPreferences_Entry<int> _forceW;
        private MelonPreferences_Entry<int> _forceH;
        private MelonPreferences_Entry<bool> _forceBorderless;
        private MelonPreferences_Entry<float> _baseAspect;

        private bool _probedThisScene;
        private bool _resApplied;
        private float _sinceScene;
        private int _hudCounter;
        private float _lastFovSet = -1f;
        private bool _loggedOverwrite;
        private bool _loggedFovOnce;

        private void BC(string s) { LoggerInstance.Msg("[bc] " + s); }

        public override void OnInitializeMelon()
        {
            _cat = MelonPreferences.CreateCategory("GeckoUltrawide");
            _enabled          = _cat.CreateEntry("Enabled", true);
            _fixFov           = _cat.CreateEntry("FixCameraFov", true);
            _fixHud           = _cat.CreateEntry("FixHudScaling", true);
            _enumerateCameras = _cat.CreateEntry("EnumerateAllCameras", false);
            _forceRes         = _cat.CreateEntry("ForceResolution", true);
            _forceW           = _cat.CreateEntry("ForceWidth", 5120);
            _forceH           = _cat.CreateEntry("ForceHeight", 1440);
            _forceBorderless  = _cat.CreateEntry("ForceBorderless", true);
            _baseAspect       = _cat.CreateEntry("BaseAspect", 16f / 9f);
            LoggerInstance.Msg("GeckoUltrawide v0.2 init. fov=" + _fixFov.Value + " hud=" + _fixHud.Value +
                               " forceRes=" + _forceRes.Value + " " + _forceW.Value + "x" + _forceH.Value);
        }

        public override void OnSceneWasLoaded(int buildIndex, string sceneName)
        {
            LoggerInstance.Msg("[Scene] #" + buildIndex + " " + sceneName);
            _probedThisScene = false;
            _resApplied = false;
            _sinceScene = 0f;
            _lastFovSet = -1f;
            _loggedOverwrite = false;
            _loggedFovOnce = false;
        }

        public override void OnLateUpdate()
        {
            try
            {
                _sinceScene += Time.deltaTime;

                if (_forceRes.Value && !_resApplied && _sinceScene > 2f) ApplyResolution();
                if (!_probedThisScene && _sinceScene > 3f) Probe();
                if (!_enabled.Value) return;
                if (_fixFov.Value) FixFov();
                if (_fixHud.Value) { _hudCounter++; if (_hudCounter >= 60) { _hudCounter = 0; FixHud(); } }
            }
            catch (Exception e) { LoggerInstance.Error("OnLateUpdate: " + e); }
        }

        private void ApplyResolution()
        {
            _resApplied = true;
            try
            {
                int w = _forceW.Value, h = _forceH.Value;
                if (Screen.width == w && Screen.height == h) { LoggerInstance.Msg("[Res] already " + w + "x" + h); return; }
                LoggerInstance.Msg("[Res] setting " + Screen.width + "x" + Screen.height + " -> " + w + "x" + h + " borderless=" + _forceBorderless.Value);
                Screen.SetResolution(w, h, _forceBorderless.Value ? FullScreenMode.FullScreenWindow : FullScreenMode.Windowed);
            }
            catch (Exception e) { LoggerInstance.Error("[Res] " + e); }
        }

        private float Aspect() { int h = Screen.height; return h > 0 ? (float)Screen.width / h : 16f / 9f; }

        // Unity's Camera.fieldOfView is the VERTICAL fov, and Unity's default behaviour is to
        // hold it constant - so a 32:9 window balloons the HORIZONTAL fov (60 vertical becomes
        // ~128 horizontal at 3.556 aspect), which is what wrecks the framing in this game.
        //
        // This returns the vertical fov whose HORIZONTAL fov equals the game's horizontal fov
        // at BaseAspect (16:9), i.e. it preserves the intended 16:9 framing while filling the
        // wider screen. Measured in-game: 60.00 -> 32.20 at 5120x1440.
        private float MatchedVerticalFov(float vfov, float aspect)
        {
            float b = _baseAspect.Value;
            if (aspect <= b + 0.001f) return vfov;
            float t = Mathf.Tan(vfov * 0.5f * Mathf.Deg2Rad) * (b / aspect);
            return Mathf.Clamp(2f * Mathf.Atan(t) * Mathf.Rad2Deg, 1f, 179f);
        }

        private void FixFov()
        {
            Camera cam = Camera.main;
            if (cam == null) return;
            if (cam.orthographic) return;
            float aspect = Aspect();
            float cur = cam.fieldOfView;

            if (_lastFovSet > 0f && Mathf.Abs(cur - _lastFovSet) < 0.01f) return; // ours stuck

            if (_lastFovSet > 0f && !_loggedOverwrite)
            {
                LoggerInstance.Msg("[FOV] game re-set fov to " + cur.ToString("F2") + " (we set " + _lastFovSet.ToString("F2") + ") - game drives fov each frame, re-applying");
                _loggedOverwrite = true;
            }

            float target = MatchedVerticalFov(cur, aspect);
            if (Mathf.Abs(target - cur) > 0.01f)
            {
                cam.fieldOfView = target;
                _lastFovSet = target;
                if (!_loggedFovOnce)
                {
                    LoggerInstance.Msg("[FOV] " + cam.name + " " + cur.ToString("F2") + " -> " + target.ToString("F2") + " (aspect " + aspect.ToString("F3") + ")");
                    _loggedFovOnce = true;
                }
            }
            else { _lastFovSet = cur; }
        }

        private void FixHud()
        {
            try
            {
                var arr = UnityEngine.Object.FindObjectsOfType(Il2CppType.Of<CanvasScaler>());
                if (arr == null) return;
                for (int i = 0; i < arr.Length; i++)
                {
                    var o = arr[i];
                    if (o == null) continue;
                    var s = o.TryCast<CanvasScaler>();
                    if (s == null) continue;
                    if (s.uiScaleMode != CanvasScaler.ScaleMode.ScaleWithScreenSize) continue;
                    if (s.screenMatchMode != CanvasScaler.ScreenMatchMode.MatchWidthOrHeight ||
                        Mathf.Abs(s.matchWidthOrHeight - 1f) > 0.001f)
                    {
                        s.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
                        s.matchWidthOrHeight = 1f; // match HEIGHT so UI keeps vertical framing
                    }
                }
            }
            catch (Exception e) { LoggerInstance.Error("[HUD] " + e); }
        }

        private void Probe()
        {
            _probedThisScene = true;
            LoggerInstance.Msg("================ PROBE ================");
            try
            {
                BC("screen");
                LoggerInstance.Msg("  Screen " + Screen.width + "x" + Screen.height + " aspect=" + Aspect().ToString("F3") + " fullScreenMode=" + Screen.fullScreenMode);

                BC("srp");
                LoggerInstance.Msg("  SRP=" + (GraphicsSettings.currentRenderPipeline != null));

                BC("Camera.main");
                var main = Camera.main;
                if (main == null) LoggerInstance.Msg("  Camera.main = NULL");
                else
                {
                    var r = main.rect;
                    LoggerInstance.Msg("  main " + main.name + " ortho=" + main.orthographic + " fov=" + main.fieldOfView.ToString("F2") +
                                       " orthoSize=" + main.orthographicSize.ToString("F2") + " aspect=" + main.aspect.ToString("F3") +
                                       " usePhysical=" + main.usePhysicalProperties +
                                       " rect=(" + r.x.ToString("F2") + "," + r.y.ToString("F2") + "," + r.width.ToString("F2") + "," + r.height.ToString("F2") + ")");
                }

                BC("allCamerasCount");
                LoggerInstance.Msg("  allCamerasCount=" + Camera.allCamerasCount);

                if (_enumerateCameras.Value)
                {
                    BC("FindObjectsOfType(Camera) - risky, opt-in");
                    var cams = UnityEngine.Object.FindObjectsOfType(Il2CppType.Of<Camera>());
                    LoggerInstance.Msg("  found " + (cams == null ? 0 : cams.Length) + " cameras");
                    if (cams != null)
                        for (int i = 0; i < cams.Length; i++)
                        {
                            var c = cams[i] == null ? null : cams[i].TryCast<Camera>();
                            if (c != null) LoggerInstance.Msg("   cam " + c.name + " ortho=" + c.orthographic + " fov=" + c.fieldOfView.ToString("F2") + " depth=" + c.depth);
                        }
                }

                BC("FindObjectsOfType(CanvasScaler)");
                var arr = UnityEngine.Object.FindObjectsOfType(Il2CppType.Of<CanvasScaler>());
                LoggerInstance.Msg("  canvasScalers=" + (arr == null ? 0 : arr.Length));
                if (arr != null)
                    for (int i = 0; i < arr.Length && i < 25; i++)
                    {
                        var s = arr[i] == null ? null : arr[i].TryCast<CanvasScaler>();
                        if (s != null)
                            LoggerInstance.Msg("   scaler " + s.name + " mode=" + s.uiScaleMode +
                                               " ref=(" + s.referenceResolution.x.ToString("F0") + "x" + s.referenceResolution.y.ToString("F0") + ")" +
                                               " match=" + s.screenMatchMode + "/" + s.matchWidthOrHeight.ToString("F2"));
                    }

                BC("probe done");
            }
            catch (Exception e) { LoggerInstance.Error("Probe: " + e); }
            LoggerInstance.Msg("=======================================");
        }
    }
}
