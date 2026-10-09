"""Native toggle-state sprint assistance; no writes/injection into the game.

RiftApart.exe 3.630.1.0, toggle sprint bound to Left Shift. See SPRINT.md.
The reader and decision logic have no Windows dependencies.
"""
from dataclasses import dataclass
import struct
import threading
import time
import json
from pathlib import Path
from runtime_config import debug_log, DEBUG
import collections

from player_tracking import HeroReader
from hero_states import find_component

RUN_TYPE_RVA = 0x6022D40
SPRINT_OFFSET = 0x1CF
RUN_LOCAL_CLASS = ".?AVHeroStateRunLocal@Hero@@"
# Classes found under the RunLocal descriptor, by what the assist may do in them.
KINDS = {
    RUN_LOCAL_CLASS: "run",
    ".?AVHeroStateHoverbootLocal@Hero@@": "hover",       # hover boots' speed mode
    ".?AVHeroStateJumpLandLocal@Hero@@": "land",
    ".?AVHeroStateJumpHoverbootLandLocal@Hero@@": "land",
}
ENABLE_KINDS = ("run", "hover", "land")      # never press Shift while grinding etc.
SIGNATURES = {
    0x7DC590: bytes.fromhex("488d05a9678405c3"),
    # Keyboard sprint action flips +1CF, then calls the native mode setter.
    0x7DEC9B: bytes.fromhex(
        "488bcf4438b3cf010000740b4488b3cf01000033d2eb0cc683cf01000001ba01000000e8ed7beeff"),
    0xFFB860: bytes.fromhex(
        "440fb749084c8bc24c8b1141ffc949c1e8044523c14963c048c1e0044903c2"
        "488b08483bca742e660f1f840000000000418d40014123c14885c9741e413bc0"
        "7419448bc0489848c1e0044903c2488b08483bca75db488b4008c333c0c3"),
}


@dataclass(frozen=True)
class SprintSample:
    identity: tuple
    sprinting: bool
    # The plain run state (not Strafe/JumpLand). Seen while fire/aim is held, it
    # marks the fire-while-sprinting lock; see SPRINT.md.
    running: bool = False
    # "run", "hover", "land" or "other" (strafe, grind, ...): see KINDS.
    kind: str = "run"


class SprintReader:
    def __init__(self, read, image_base):
        self.hero = HeroReader(read, image_base)
        self.base = image_base
        self.profile_ok = None
        self.status = "waiting for gameplay"
        self.class_names = {}

    def class_name(self, vtable):
        """MSVC RTTI type name for a vtable, cached per vtable."""
        if vtable not in self.class_names:
            name = None
            col = self.hero._bytes(vtable - 8, 8)
            raw = self.hero._bytes(struct.unpack("<Q", col)[0], 16) if col else None
            if raw and struct.unpack_from("<I", raw)[0] == 1:
                text = self.hero._bytes(self.base + struct.unpack_from("<I", raw, 12)[0] + 0x10, 64)
                name = text.split(b"\0")[0].decode("ascii", "replace") if text else None
            if name is None:
                return None
            self.class_names[vtable] = name
        return self.class_names[vtable]

    def component(self, entity):
        """Reproduce the game's bounded, linear-probing component hash lookup."""
        return find_component(self.hero._bytes, entity, self.base + RUN_TYPE_RVA)

    def sample(self):
        if self.profile_ok is None:
            self.profile_ok = all(
                self.hero._bytes(self.base + r, len(code)) == code
                for r, code in SIGNATURES.items())
        if not self.profile_ok:
            self.status = "unsupported sprint code; assist disabled"
            return None
        hero = self.hero.sample()
        if hero is None:
            self.status = self.hero.status
            return None
        result = self.component(hero.entity)
        if result is None:
            self.status = "no active run state"
            return None
        ptr, table_header, slot, entry = result
        raw = self.hero._bytes(ptr, SPRINT_OFFSET + 1)
        if raw is None:
            return None
        vt = struct.unpack_from("<Q", raw)[0]
        owner = struct.unpack_from("<Q", raw, 0x10)[0]
        # Local run subclasses share the traced sprint-input update routine.
        callbacks = self.hero._bytes(vt + 0x100, 8)
        expected = struct.pack("<Q", self.base + 0x7DEAF0)
        if owner != hero.entity or callbacks != expected or raw[SPRINT_OFFSET] not in (0, 1):
            self.status = "unrecognized run state; assist inactive"
            return None
        again = self.hero.sample()
        if (again is None or (again.handle, again.entity) != (hero.handle, hero.entity)
                or self.hero._bytes(hero.entity + 0x80, 10) != table_header
                or self.hero._bytes(slot, 16) != entry
                or self.hero._bytes(ptr, 0x18) != raw[:0x18]
                or self.hero._bytes(ptr + SPRINT_OFFSET, 1) != raw[SPRINT_OFFSET:]):
            return None
        sprinting = bool(raw[SPRINT_OFFSET])
        kind = KINDS.get(self.class_name(vt), "other")
        self.status = ("hovering" if kind == "hover" and sprinting else
                       "sprinting" if sprinting else "not sprinting")
        return SprintSample((hero.handle, hero.entity), sprinting, kind == "run", kind)


MODES = ("always", "normal")
SETTINGS_PATH = Path(__file__).with_name("sprint_settings.json")


def _load_settings(path=SETTINGS_PATH):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def load_mode(path=SETTINGS_PATH):
    mode = _load_settings(path).get("mode")
    return mode if mode in MODES else "always"


def load_hover_boots(path=SETTINGS_PATH):
    return _load_settings(path).get("hover_boots") is True


def save_settings(path=SETTINGS_PATH, **changes):
    data = _load_settings(path)
    data.update(changes)
    if data.get("mode", "always") not in MODES:
        raise ValueError("invalid sprint mode")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_mode(mode, path=SETTINGS_PATH):
    if mode not in MODES:
        raise ValueError("invalid sprint mode")
    save_settings(path, mode=mode)


class SprintGate:
    """Choose a direction from the native toggle, never guessed Shift parity.

    Actions: "cancel" (toggle on while firing/aiming), "unstick" (the game's
    fire-while-sprinting lock: toggle already off but the plain run state keeps
    returning while fire/aim is held) and "enable" (Always mode).

    The lock happens when the game handles the click before our cancel: it clears
    the toggle itself on that frame. So a press that began while sprinting and
    now reads off, without our cancel, is unstuck at once; repeated plain-run
    sightings are the fallback signal."""
    STUCK_AFTER = 0.03     # ignore the run state's normal last frame after a press
    STUCK_SAMPLES = 3      # run-state sightings needed before acting
    ENABLE_AFTER = 0.15    # moving with sprint off this long -> enable

    def __init__(self, hover_boots=False):
        # Once the hero has hover boots, Shift is hover (speed mode, only while held)
        # instead of sprint; Always mode then turns Shift into a hover toggle (HoverToggle).
        self.hover_boots = hover_boots
        self.off_since = None
        self.identity = None
        self.last_action = None
        self.next_action = 0.0
        self.combat_since = None
        self.stuck_seen = 0
        self.was_sprinting = False   # last valid reading before fire/aim
        self.armed = False           # this press began while sprinting

    def update(self, now, sample, combat, allowed, shift=False,
               moving=False, mode="always"):
        if not combat:
            self.combat_since = None
            self.stuck_seen = 0
            self.armed = False
        elif self.combat_since is None:
            self.combat_since = now
            self.armed = self.was_sprinting
        if sample is None or not allowed:
            self.off_since = None
            self.identity = None
            return None
        if sample.identity != self.identity:
            self.off_since = None
            self.stuck_seen = 0
            self.was_sprinting = self.armed = False
            self.identity = sample.identity
        if sample.kind == "hover":
            self.hover_boots = True
        on = sample.sprinting
        if not combat:
            self.was_sprinting = sample.sprinting
        if on or combat or not moving:
            self.off_since = None
        elif self.off_since is None:
            self.off_since = now
        if (combat and sample.running and not sample.sprinting
                and now - self.combat_since >= self.STUCK_AFTER):
            self.stuck_seen += 1
        desired = None
        if combat and sample.sprinting:
            desired = "cancel"
        elif combat and (self.armed or self.stuck_seen >= self.STUCK_SAMPLES):
            desired = "unstick"
        elif (mode == "always" and not combat and moving and not on
              and sample.kind in ENABLE_KINDS and self.off_since is not None
              and now - self.off_since >= self.ENABLE_AFTER and not self.hover_boots):
            # With hover boots, Shift toggles hover instead (HoverToggle); no auto start.
            desired = "enable"
        if shift or desired is None:
            return None
        # A new combat action can cancel a recent auto-enable immediately.
        if now < self.next_action and not (desired != "enable" and self.last_action == "enable"):
            return None
        self.last_action = desired
        self._undo = (self.armed, self.stuck_seen)
        self.stuck_seen = 0
        if desired != "enable":
            self.armed = False
        self.next_action = now + (.60 if desired == "enable" else .30)
        return desired

    def not_sent(self, now):
        # The pulse was skipped (state/focus raced): keep what made us act, so the
        # next poll can act again instead of falling back to the slower signal.
        self.next_action = now
        self.armed, self.stuck_seen = getattr(self, "_undo", (self.armed, self.stuck_seen))


class HoverToggle:
    """Hover boots as a toggle. The game only hovers while Shift is held (+~0.2 s), so
    while hover is "on" we keep Shift held. The user's own (physical) Shift press flips
    it on/off. A physical release also releases the key for the game, so we press it
    again at once (measured: a 30 ms gap does not interrupt hover). Aim releases Shift
    and hover resumes after aiming; menus, map, cutscenes and focus loss turn it off."""

    def __init__(self):
        self.on = False
        self.holding = False        # our injected Shift is down
        self.physical = False       # the user's Shift is down

    def physical_key(self, down):
        """A physical Shift edge (from raw input). Returns True if it flipped hover."""
        if down and not self.physical:
            self.physical = True
            self.on = not self.on
            return True
        if not down and self.physical:
            self.physical = False
            self.holding = False    # the key-up reached the game: our hold is gone too
        return False

    def want_hold(self, allowed, aim):
        if not allowed:
            self.on = False
        return self.on and not aim and not self.physical


class RawShift:
    """Physical Shift edges via Windows Raw Input (RIDEV_INPUTSINK on a message-only
    window). Injected keys arrive with hDevice == 0, so our own presses are ignored.
    Unlike a low-level hook this is not in the system input path."""

    def __init__(self):
        self.events = collections.deque()
        self.ok = False
        threading.Thread(target=self._run, name="raw-shift", daemon=True).start()

    def _run(self):
        import ctypes as c
        from ctypes import wintypes as w
        u32 = c.WinDLL("user32", use_last_error=True)
        u32.CreateWindowExW.restype = w.HWND
        u32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int,
                                        c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
        hwnd = u32.CreateWindowExW(0, "STATIC", "rift-raw-shift", 0, 0, 0, 0, 0, w.HWND(-3), None, None, None)
        if not hwnd:
            return

        class RAWINPUTDEVICE(c.Structure):
            _fields_ = [("usUsagePage", w.USHORT), ("usUsage", w.USHORT),
                        ("dwFlags", w.DWORD), ("hwndTarget", w.HWND)]

        class RAWINPUTHEADER(c.Structure):
            _fields_ = [("dwType", w.DWORD), ("dwSize", w.DWORD),
                        ("hDevice", w.HANDLE), ("wParam", w.WPARAM)]

        class RAWKEYBOARD(c.Structure):
            _fields_ = [("MakeCode", w.USHORT), ("Flags", w.USHORT), ("Reserved", w.USHORT),
                        ("VKey", w.USHORT), ("Message", w.UINT), ("ExtraInformation", w.ULONG)]

        class RAWINPUT(c.Structure):
            _fields_ = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD)]

        dev = RAWINPUTDEVICE(1, 6, 0x00000100, hwnd)          # keyboard, RIDEV_INPUTSINK
        if not u32.RegisterRawInputDevices(c.byref(dev), 1, c.sizeof(dev)):
            return
        self.ok = True
        u32.GetRawInputData.argtypes = [w.HANDLE, w.UINT, c.c_void_p, c.POINTER(w.UINT), w.UINT]
        msg = w.MSG()
        data = RAWINPUT()
        while u32.GetMessageW(c.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x00FF:                            # WM_INPUT
                size = w.UINT(c.sizeof(data))
                if u32.GetRawInputData(msg.lParam, 0x10000003, c.byref(data), c.byref(size),
                                       c.sizeof(RAWINPUTHEADER)) not in (0, 0xFFFFFFFF):
                    kb = data.keyboard
                    if (data.header.dwType == 1 and data.header.hDevice
                            and (kb.VKey == 0x10 or kb.MakeCode in (0x2A, 0x36))):
                        self.events.append(not (kb.Flags & 1))   # RI_KEY_BREAK = up
            u32.TranslateMessage(c.byref(msg))
            u32.DispatchMessageW(c.byref(msg))


class WindowsInput:
    def __init__(self, game_pid):
        import ctypes as c
        from ctypes import wintypes as w
        self.c, self.w, self.pid = c, w, game_pid
        self.u32 = c.WinDLL("user32", use_last_error=True)
        class KEYBDINPUT(c.Structure):
            _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("extra", c.c_size_t)]
        class MOUSEINPUT(c.Structure):
            _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("data", w.DWORD),
                        ("flags", w.DWORD), ("time", w.DWORD), ("extra", c.c_size_t)]
        class UNION(c.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
        class INPUT(c.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", w.DWORD), ("u", UNION)]
        self.INPUT, self.KEYBDINPUT = INPUT, KEYBDINPUT
        self.u32.SendInput.argtypes = [w.UINT, c.POINTER(INPUT), c.c_int]
        self.u32.SendInput.restype = w.UINT
        self.u32.GetAsyncKeyState.argtypes = [c.c_int]
        self.u32.GetAsyncKeyState.restype = c.c_short
        self.u32.GetForegroundWindow.restype = w.HWND
        self.u32.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        self.u32.GetWindowThreadProcessId.restype = w.DWORD
        self.injected_down = False

    def focused(self):
        pid = self.w.DWORD()
        self.u32.GetWindowThreadProcessId(self.u32.GetForegroundWindow(), self.c.byref(pid))
        return pid.value == self.pid

    def held(self, vk):
        return bool(self.u32.GetAsyncKeyState(vk) & 0x8000)

    def shift(self, down):
        event = self.INPUT(type=1)
        event.ki = self.KEYBDINPUT(0, 0x2A, 0x0008 | (0 if down else 0x0002), 0, 0)
        if self.u32.SendInput(1, self.c.byref(event), self.c.sizeof(event)) != 1:
            raise OSError(self.c.get_last_error(), "SendInput failed")
        self.injected_down = down


class SprintAssist:
    def __init__(self, read, image_base, game_pid, gameplay_allowed, input_device=None):
        self.reader = SprintReader(read, image_base)
        self.input = input_device or WindowsInput(game_pid)
        self.allowed = gameplay_allowed
        self.stop_event = threading.Event()
        self.thread = None
        self.mode = load_mode()

    @property
    def mode_label(self):
        return "Always sprint" if self.mode == "always" else "Normal sprint"

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._run, name="sprint-assist", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _combat(self, hovering):
        aim = self.input.held(0x02)
        return aim if hovering else aim or self.input.held(0x01)

    def _run(self):
        gate = SprintGate(hover_boots=load_hover_boots())
        hover_saved = gate.hover_boots
        hover = HoverToggle()
        raw_shift = RawShift() if isinstance(self.input, WindowsInput) else None
        hold_released = 0.0
        last_status = None
        release_at = None
        last_f8 = False
        def log(message):
            debug_log(f"[sprint {time.monotonic():.3f}] {message}", flush=True)
        log(self.mode_label + "; F8 switches mode; native sprint-toggle detection")
        # --debug only: last ~3 s of decisions, written out when a fire/aim lock lasts
        # more than 0.25 s (plain run state keeps returning while the button is held).
        trace = collections.deque(maxlen=300) if DEBUG else None
        lock_start = last_run = None
        dumped = False
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                focused = self.input.focused()
                f8 = self.input.held(0x77)
                if focused and f8 and not last_f8:
                    self.mode = "normal" if self.mode == "always" else "always"
                    try:
                        save_mode(self.mode)
                    except OSError as exc:
                        log("could not save mode: " + str(exc))
                    log(self.mode_label)
                last_f8 = f8
                if release_at is not None and (now >= release_at or not focused):
                    self.input.shift(False)
                    release_at = None
                allowed = focused and self.allowed()
                sample = self.reader.sample() if allowed else None
                status = self.reader.status if allowed else "inactive (focus/map)"
                if status != last_status:
                    log(status)
                    last_status = status
                hovering_mode = gate.hover_boots and self.mode == "always"
                events = []
                while raw_shift is not None and raw_shift.events:
                    events.append(raw_shift.events.popleft())
                for down in events:
                    if hover.physical_key(down) and hovering_mode:
                        log("hover " + ("on" if hover.on else "off") + " (Shift)")
                if not hovering_mode:
                    hover.on = False
                # While hover is on, left click is the hover boost (3 clicks speed up), so
                # only right click (aim) counts as combat. Otherwise fire or aim.
                combat = self._combat(hover.on)
                aim = self.input.held(0x02)
                moving = any(self.input.held(vk) for vk in (0x57, 0x41, 0x53, 0x44))
                want = hover.want_hold(allowed, aim)
                if want and not hover.holding and release_at is None:
                    self.input.shift(True)
                    hover.holding = True
                elif not want and hover.holding:
                    if not hover.physical:
                        self.input.shift(False)
                        hold_released = now
                    hover.holding = False
                # Shift is busy if the user holds it, we hold it, a tap is in flight, or
                # we just released it (the game samples per frame: a tap right after the
                # release would merge with the hold and be ignored).
                shift = (hover.physical or hover.holding or release_at is not None
                         or (raw_shift is None and self.input.held(0x10))
                         or now - hold_released < 0.04)
                action = gate.update(now, sample, combat, allowed, shift, moving, self.mode)
                if gate.hover_boots and not hover_saved:
                    hover_saved = True
                    log("hover boots detected: Shift now toggles hover (auto sprint off)")
                    try:
                        save_settings(hover_boots=True)
                    except OSError as exc:
                        log("could not save hover boots: " + str(exc))
                if action:
                    # Revalidate immediately before sending the key; no delayed cached state.
                    fresh = self.reader.sample()
                    fresh_combat = self._combat(hover.on)
                    intent = (fresh_combat if action in ("cancel", "unstick") else
                              not fresh_combat and self.mode == "always" and
                              any(self.input.held(vk) for vk in (0x57, 0x41, 0x53, 0x44)))
                    # Compare the toggle only: the lock alternates Run/Strafe every frame.
                    same = (fresh is not None and fresh.identity == sample.identity
                            and fresh.sprinting == sample.sprinting)
                    if (same and self.input.focused() and self.allowed()
                            and intent and not hover.holding and not hover.physical):
                        self.input.shift(True)
                        release_at = time.monotonic() + 0.08
                        log("sent sprint " + action)
                    else:
                        gate.not_sent(time.monotonic())
                        action = "skipped " + action + (
                            f" (fresh={fresh and (int(fresh.sprinting), int(fresh.running))}"
                            f" intent={int(bool(intent))})")
                if trace is not None:
                    trace.append((round(now, 3), int(allowed), status,
                                  None if sample is None else (int(sample.sprinting), int(sample.running)),
                                  int(combat), int(moving), int(shift), int(gate.armed), action or ""))
                    if combat and sample is not None and sample.running and not sample.sprinting:
                        lock_start = lock_start or now
                        last_run = now
                    if lock_start and (not combat or now - last_run > 0.1):
                        lock_start, dumped = None, False
                    if lock_start and last_run - lock_start > 0.25 and not dumped:
                        dumped = True
                        with open("../research/sprint_lock.log", "a") as f:
                            f.write(f"=== lock {last_run - lock_start:.2f}s at {time.strftime('%H:%M:%S')} "
                                    f"mode={self.mode}\n")
                            f.write("t, allowed, status, (toggle, plain-run), combat, moving, shift, armed, action\n")
                            for row in trace:
                                f.write(repr(row) + "\n")
                # The toggle is persistent; do not chase transient animation flags.
                time.sleep(0.012 if allowed else 0.05)
        except Exception as exc:
            debug_log("[sprint] assist stopped:", repr(exc), flush=True)
        finally:
            if self.input.injected_down:
                try:
                    self.input.shift(False)
                except Exception as exc:
                    debug_log("[sprint] key release failed:", repr(exc), flush=True)
