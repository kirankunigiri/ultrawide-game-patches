# Rift Apart collectibles minimap - external overlay, read-only memory access.
# - Player position/facing: the native pause map's generation-checked hero transform.
# - Icons: the pause map's own icon array. Whenever the pause map is open, every visible,
#   unclamped icon is converted to a world position (map px = world X/Z * SCALE, centred
#   on the player) and remembered. The minimap then tracks them against the live player.
import ctypes, json, struct, time
from mem import read, EXE
from arr import icons
import overlay
import heroread
import threading
from runtime_config import debug_log, DEBUG

MAP_BASE = 0x1ace96e7168
SCALE = 1.5655            # pause-map px per world unit (default zoom), Sargasso
SCALES_FILE = "map_scales.json"   # native map id -> measured pause-map px per world unit
SNAPS_FILE = "map_scale_snaps.json"   # last pause-map opening per uncalibrated map
CENTER = (960.0, 540.0)   # player position on the pause map canvas
RADIUS_WORLD = 190.0      # world units shown from centre to edge (square minimap)
SIZE = 360                # minimap width/height in px
STATE_FILE = "minimap_icons.json"

SKIP = ("player",)          # drawn separately, rotated to the live heading


# ---- planet map art: the game's own map textures, aligned to world X/Z ----
# maps.json: native map id (fog/pause-map key) -> extracted texture + exact MapMin/MapMax
# bounds from the game's fog record. The active map follows current_map_key().
from PIL import Image, ImageDraw, ImageEnhance, ImageTk
KEY_RGB = (1, 2, 3)                       # overlay.KEY - fully transparent
MAPS_FILE = "maps.json"
_pad = 1024
MAP = None                                # active map (None: no art for this map)
MAP_KEY = None                            # native id MAP belongs to
_b = None                                 # active map's registry entry (bounds)
try:
    _registry = json.load(open(MAPS_FILE))
except Exception as _e:
    _registry = {}
    debug_log("no map registry:", _e)

def _build_map(entry):
    img = Image.open(entry["texture"]).convert("RGB")
    fill = img.getchannel("G").point(lambda v: 255 if 8 < v < 40 else 0)   # land fill, not outline
    img = ImageEnhance.Brightness(img).enhance(2.6)            # textures are navy-on-navy
    ppu = img.size[0] / (entry["x_max"] - entry["x_min"])
    # pad with the map's own background colour so views past the texture edge aren't black
    big = Image.new("RGB", (img.size[0] + 2 * _pad, img.size[1] + 2 * _pad), img.getpixel((4, 4)))
    big.paste(img, (_pad, _pad))
    bigfill = Image.new("L", big.size, 0)
    bigfill.paste(fill, (_pad, _pad))
    return dict(img=big, fill=bigfill, x0=entry["x_min"] - _pad / ppu, z0=entry["z_min"] - _pad / ppu,
                ppu=ppu, bg=img.getpixel((4, 4)), key=None,
                extent=max(entry["x_max"] - entry["x_min"], entry["z_max"] - entry["z_min"]))

_photo = None                              # keep a reference or Tk drops the image
_mask_cache = {}

# Heading is read from the same validated native transform as the position.
facing_offset = 0.0
try:
    facing_offset = json.load(open("facing_offset.json"))["offset"]
except Exception:
    pass


def facing_deg():
    y = heroread.hero_heading()
    return y + facing_offset if y is not None else None

# ---- explored area: the game's own fog-of-war grid, read the way the pause map reads it ----
# (GUI2::PauseMenuElementMapPage::InitMapTextures - see fogread.py). Refreshed every second,
# so the minimap shows exactly what the pause map shows, including all past exploration.
from PIL import ImageFilter
import fogread
EXPLORE_RES = 4                            # mask px = padded texture px / 4
explored = None
_fog_t = 0.0

def current_map_key():
    """Native ID of the current map, or None when the game has no map ("MAP OFFLINE")."""
    B = EXE.lpBaseOfDll
    try:
        P = struct.unpack("<Q", read(B + 0x51615c8, 8))[0]
        idx = struct.unpack("<i", read(P, 4))[0]
        A = struct.unpack("<Q", read(B + 0x51f1e90, 8))[0]
        ids = struct.unpack("<Q", read(A + 0x18, 8))[0]
        return struct.unpack("<I", read(ids + idx * 4, 4))[0]
    except (TypeError, struct.error):
        return None

def map_supported():
    """Select the art for the current native map; False when there is none (or map offline)."""
    return select_map(current_map_key())

def select_map(key):
    global MAP, MAP_KEY, _b, MAP_BG, explored, _styled, _plain, remembered
    if key == MAP_KEY:
        return MAP is not None
    MAP_KEY, MAP, _b, explored, _styled = key, None, None, None, None
    remembered = _icons.setdefault(f"{key:#x}", {}) if key is not None else {}
    if key is not None and f"{key:#x}" not in _registry:
        try:                                     # new planets can be added while running
            _registry.update(json.load(open(MAPS_FILE)))
        except Exception:
            pass
    entry = _registry.get(f"{key:#x}") if key is not None else None
    if entry:
        try:
            m = _build_map(entry)
            m["key"] = key
            MAP, _b, MAP_BG = m, entry, tuple(m["bg"])
            _plain = (m["img"], {})
            threading.Thread(target=_build_plain, args=(m,), name="map-prescale", daemon=True).start()
        except Exception as exc:
            debug_log("map load failed:", key, exc)
    return MAP is not None

def refresh_fog():
    """Rebuild the explored mask (padded-texture space / EXPLORE_RES) from the game's grid."""
    global explored, _fog_t
    if MAP is None or time.time() - _fog_t < 1.0:
        return
    _fog_t = time.time()
    try:
        if current_map_key() != MAP_KEY:
            return                                                # select_map runs in draw
        rec = dict(fogread.table()).get(MAP_KEY)
        g = fogread.grid(rec)
        w, h = MAP["img"].size
        tw = (w - 2 * _pad) // EXPLORE_RES
        fog = Image.fromarray((g * 255).astype("uint8")).resize((tw, tw), Image.BILINEAR)
        m = Image.new("L", (w // EXPLORE_RES, h // EXPLORE_RES), 0)
        m.paste(fog, (_pad // EXPLORE_RES, _pad // EXPLORE_RES))
        if explored is None or m.tobytes() != explored.tobytes():
            explored = m
            _restyle(MAP, m)
    except Exception:
        pass                                                      # keep the last good mask

# Pause-map fog style applied once to the whole padded texture whenever the game's fog
# grid changes, off the Tk thread. Each frame then only crops and scales (fast).
_styled = None              # (source image, {texture px per output px: pre-scaled copy})
_style_lock = threading.Lock()
_style_pending = None

def radius_world(m=None):
    """Minimap: world units from centre to edge. 190 on large maps (Sargasso), closer on
    small ones so the map is not a speck (about 30% of the map's extent)."""
    m = m or MAP
    return RADIUS_WORLD if m is None else min(RADIUS_WORLD, max(60.0, m["extent"] * 0.3))

def full_height_world(m=None):
    """Fullscreen: world units top to bottom. 1050 on large maps, ~the whole map on small ones."""
    m = m or MAP
    return FULL_HEIGHT_WORLD if m is None else min(FULL_HEIGHT_WORLD, max(200.0, m["extent"] * 1.15))

def _view_scales(m):
    """Texture px per output px for the two fixed zooms (minimap, fullscreen)."""
    screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    return (radius_world(m) / (SIZE / 2) * m["ppu"], full_height_world(m) / screen_h * m["ppu"])

def _prescaled(m, src):
    """src plus copies already scaled to each view's zoom, so a frame is just a crop."""
    return src, {round(k, 4): src.resize((round(src.size[0] / k), round(src.size[1] / k)), Image.BILINEAR)
                 for k in _view_scales(m)}

def _build_plain(m):
    global _plain
    result = _prescaled(m, m["img"])
    if MAP is m:                       # the map may have changed meanwhile
        _plain = result

def _style_full(m, mask):
    from PIL import ImageChops
    im = m["img"]
    e = mask.resize(im.size, Image.BILINEAR)
    # explored land = light lavender fill, unexplored land = darker, crisp edges
    e = e.point(lambda v: 255 if v >= 128 else 0).filter(ImageFilter.GaussianBlur(1.0))
    out = Image.composite(ImageEnhance.Brightness(im).enhance(1.15), ImageEnhance.Brightness(im).enhance(0.7), e)
    lav = Image.blend(im, Image.new("RGB", im.size, (196, 178, 246)), 0.85)
    return Image.composite(lav, out, ImageChops.multiply(e, m["fill"]))

def _style_worker():
    global _styled, _style_pending
    while True:
        with _style_lock:
            job, _style_pending = _style_pending, None
        if job is None:
            return
        m, mask = job
        try:
            result = _prescaled(m, _style_full(m, mask))
            if MAP is m:
                _styled = result
        except Exception as exc:
            debug_log("fog styling failed:", exc)

def _restyle(m, mask):
    global _style_pending
    with _style_lock:
        busy = _style_pending is not None
        _style_pending = (m, mask)
    if not busy:
        threading.Thread(target=_style_worker, name="fog-style", daemon=True).start()

_icons = {}               # native map id -> {marker key -> dict(img, x, z, done)}
try:
    _icons = json.load(open(STATE_FILE))
    if any("img" in v for v in _icons.values()):        # pre-multi-map file: Sargasso only
        _icons = {"0xbd52b112": _icons}
except Exception:
    pass
remembered = {}           # markers of the active map (set by select_map)

user32 = ctypes.windll.user32
pid = None
try:
    import pymem
    pid = pymem.Pymem("RiftApart.exe").process_id
except Exception:
    pass

def game_focused():
    h = user32.GetForegroundWindow()
    p = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value == pid

ICON_DIR = "icons"
_icon_src = {}            # lower-case icon name -> RGBA image (the game's own map icon art)
_icon_cache = {}          # (name, size, angle) -> scaled/rotated image

def icon_file(img):
    n = img.lower()
    for cand in (n, n.replace("mapicon", "collectible")):
        try:
            return cand, Image.open(f"{ICON_DIR}/{cand}.png").convert("RGBA")
        except Exception:
            pass
    return None, None

def icon(img, size, angle=0):
    key = (img.lower(), size, int(round(angle)))
    if key not in _icon_cache:
        if img.lower() not in _icon_src:
            _icon_src[img.lower()] = icon_file(img)[1]
        src = _icon_src[img.lower()]
        if src is None:
            return None
        im = src.resize((size, size), Image.LANCZOS)
        if angle:
            im = im.rotate(-angle, resample=Image.BICUBIC, expand=False)
        _icon_cache[key] = im
    return _icon_cache[key]

def style_for(img):
    """True if this map icon should be shown (it has art and isn't the player)."""
    low = img.lower()
    if any(s in low for s in SKIP):
        return None
    return True if icon(img, 24) is not None else None

last_capture = 0.0
_captured_this_open = False
VIEW = (115.2, 216.0, 1804.8, 1000.0)   # map viewport on the 1920x1080 UI canvas

def capture(p):
    """Pause map open: convert visible, unclamped icons to world positions."""
    global last_capture, _captured_this_open
    if _captured_this_open:
        return                 # once per open: later frames may be zoomed/panned by the player
    _captured_this_open = True
    last_capture = time.time()
    if map_base() is None:
        return
    ic = icons(map_base())
    # Measure from the player's own icon: it is only at CENTER until the map is panned.
    me = next((d for d in ic if "player" in d["img"].lower() and d["vis"]), None)
    if me is None:
        return
    ref = (me["x"], me["y"])
    S = map_scale(p, me, ic)
    if S is None:
        return
    # calibrate facing: the map's player icon rotation is the truth
    global facing_offset
    raw = facing_deg()
    if raw is not None:
        raw -= facing_offset
        off = ((me["rot"] - raw + 180) % 360) - 180
        # only a fine correction: the forward axis itself is learned from movement
        if abs(off) < 25 and abs(off - facing_offset) > 2:
            facing_offset = off
            json.dump({"offset": off}, open("facing_offset.json", "w"))
    # everything inside the visible map area is re-read now: forget older markers there
    vx0 = p[0] + (VIEW[0] - ref[0]) / S; vx1 = p[0] + (VIEW[2] - ref[0]) / S
    vz0 = p[1] + (VIEW[1] - ref[1]) / S; vz1 = p[1] + (VIEW[3] - ref[1]) / S
    for k in [k for k, v in remembered.items() if "x" in v and vx0 < v["x"] < vx1 and vz0 < v["z"] < vz1]:
        del remembered[k]
    for d in ic:
        if not d["vis"] or d["arrow"] or style_for(d["img"]) is None:
            continue
        wx = p[0] + (d["x"] - ref[0]) / S
        wz = p[1] + (d["y"] - ref[1]) / S
        # same icon type within 3 units = same icon (updates instead of duplicating)
        key = next((k for k, v in remembered.items() if v.get("img") == d["img"] and "x" in v
                    and abs(v["x"] - wx) < 3 and abs(v["z"] - wz) < 3), f"{d['img']}@{round(wx)}_{round(wz)}")
        remembered[key] = dict(img=d["img"], x=wx, z=wz, done=d["done"],
                               cap=[p[0], p[1], d["x"] - ref[0], d["y"] - ref[1]])
    # clamped objectives: remember only the direction they were in
    for d in ic:
        if d["vis"] and d["arrow"] and "objective" in d["img"].lower():
            remembered["objective_dir"] = dict(img=d["img"], dirx=d["x"] - ref[0], diry=d["y"] - ref[1], done=0)
    json.dump(_icons, open(STATE_FILE, "w"), indent=1)

# ---- pause-map scale (canvas px per world unit) per map ----
# Icon canvas position relative to the player's icon = (icon world - player world) * S.
# Opening the map at two spots d world units apart moves every fixed icon by d * S, so
# two openings measure S for any map. Sargasso's calibrated value is the default.
_scales = {"0xbd52b112": SCALE}
try:
    _scales.update(json.load(open(SCALES_FILE)))
except Exception:
    pass
_scale_snap = {}          # map id -> (player xz, {icon id: canvas offset from player icon})
try:
    _scale_snap = {k: (tuple(v[0]), {int(i): tuple(o) for i, o in v[1].items()})
                   for k, v in json.load(open(SNAPS_FILE)).items()}
except Exception:
    pass

def provisional_scale():
    """Until measured: the pause map draws its 2048 px texture at the same canvas size on
    every planet (true for Sargasso: 1.5655 px/unit over 1112 units), so S ~ 1741 / width."""
    return SCALE * 1112.0 / (_b["x_max"] - _b["x_min"]) if _b else SCALE

def map_scale(p, me, ic):
    """Measured canvas px per world unit for the active map, else the provisional value."""
    k = f"{MAP_KEY:#x}" if MAP_KEY is not None else None
    if k is None:
        return None
    if k in _scales:
        return _scales[k]
    rel = {d["id"]: (d["x"] - me["x"], d["y"] - me["y"]) for d in ic
           if d["vis"] and not d["arrow"] and d is not me and d["id"]}
    prev = _scale_snap.get(k)
    if prev is not None:
        (px, pz), old = prev
        dx, dz = p[0] - px, p[1] - pz
        moved = (dx * dx + dz * dz) ** 0.5
        if moved >= 8.0:
            ratios = []
            for i, (ox, oy) in old.items():
                if i in rel:
                    cx, cy = rel[i][0] - ox, rel[i][1] - oy
                    # icons move opposite to the player: cx = -dx*S, cy = -dz*S
                    if cx * dx <= 0 and cy * dz <= 0:
                        ratios.append(((cx * cx + cy * cy) ** 0.5) / moved)
            ratios.sort()
            if ratios and ratios[-1] - ratios[0] < 0.05 * ratios[len(ratios) // 2]:
                _scales[k] = ratios[len(ratios) // 2]
                json.dump({key: v for key, v in _scales.items() if key != "0xbd52b112"},
                          open(SCALES_FILE, "w"), indent=1)
                debug_log(f"pause-map scale for {k}: {_scales[k]:.4f} from {len(ratios)} icons "
                          f"(provisional was {provisional_scale():.4f})")
                _rescale_markers(_scales[k])
                return _scales[k]
    _scale_snap[k] = (p, rel)
    try:
        json.dump({key: [list(v[0]), v[1]] for key, v in _scale_snap.items()}, open(SNAPS_FILE, "w"))
    except Exception:
        pass
    return provisional_scale()

def _rescale_markers(S):
    """Markers stored with the provisional scale keep their raw capture; redo them with S."""
    for d in remembered.values():
        if "cap" in d:
            px, pz, cx, cy = d["cap"]
            d["x"], d["z"] = px + cx / S, pz + cy / S
    json.dump(_icons, open(STATE_FILE, "w"), indent=1)

# ---- the pause map's icon array: found by signature, re-found if it ever moves ----
import re as _re
from mem import regions as _regions

def _is_player_record(addr):
    r = read(addr, 0x88)
    return bool(r) and struct.unpack_from("<i", r, 0)[0] == 2 and b"MapIconPlayer" in r[4:0x84]

def locate_map_base():
    """Array start = the player's icon record (type 2, MapIconPlayer) with an empty slot before it."""
    pat = _re.compile(rb"coui://[ -~]{0,100}MapIconPlayer\.texture\x00")
    for base, size in _regions():
        # Bound allocation and memory-copy pressure; overlap covers split URIs.
        for offset in range(0, size, 1024 * 1024):
            start = max(0, offset - 256)
            b = read(base + start, min(size - start, 1024 * 1024 + 256))
            if b:
                for m in pat.finditer(b):
                    rec = base + start + m.start() - 4
                    prev = read(rec - 0xE8 + 4, 8)
                    if _is_player_record(rec) and prev == bytes(8):
                        return rec
            time.sleep(.001)
    return None

_mapbase = {"addr": MAP_BASE if _is_player_record(MAP_BASE) else None,
            "searching": False, "retry_at": 0.0}

def _find_map_base_worker():
    try:
        a = locate_map_base()
        if a:
            _mapbase["addr"] = a
    finally:
        _mapbase["retry_at"] = time.monotonic() + 30.0
        _mapbase["searching"] = False

def map_base():
    a = _mapbase["addr"]
    if a and _is_player_record(a):
        return a
    _mapbase["addr"] = None
    if not _mapbase["searching"] and time.monotonic() >= _mapbase["retry_at"]:
        _mapbase["searching"] = True
        threading.Thread(target=_find_map_base_worker, daemon=True).start()
    return None

def map_open():
    a = map_base()
    r = read(a, 0x88) if a else None
    return bool(r) and r[0x84] == 1     # player icon visible = pause map showing

# ---------------------------------------------------------------------------------------
# rendering: one PIL image per view (map art + explored shading + game icons + player)
# ---------------------------------------------------------------------------------------
FULL_HEIGHT_WORLD = 1050.0   # fullscreen view: world units from top to bottom of the screen
ALPHA = 0.7                 # overlay opacity, both views
_alpha_set = False
fullscreen = False
_sprint_context = (0.0, False)


def sprint_gameplay_allowed():
    updated, allowed = _sprint_context
    return allowed and time.monotonic() - updated < 0.75

_key_was_down = False
_last_render = None         # (mode, p, heading, n_icons) of what is on screen
_view_photo = None         

def _crop_fill(img, box, fill):
    """crop() that fills anything outside the image with `fill` (PIL pads with black)."""
    x0, y0, x1, y1 = box
    out = Image.new(img.mode, (x1 - x0, y1 - y0), fill)
    ix0, iy0 = max(0, x0), max(0, y0)
    ix1, iy1 = min(img.size[0], x1), min(img.size[1], y1)
    if ix1 > ix0 and iy1 > iy0:
        out.paste(img.crop((ix0, iy0, ix1, iy1)), (ix0 - x0, iy0 - y0))
    return out

def _background(p, out_w, out_h, units_per_px, sub=None):
    """Styled map art around p for an out_w x out_h view; sub=(x, y, w, h) renders only
    that part of the view."""
    sx, sy, sw, sh = sub or (0, 0, out_w, out_h)
    if MAP is None:
        return Image.new("RGB", (sw, sh), (12, 10, 40))
    ppu = MAP["ppu"]
    k = units_per_px * ppu                                   # texture px per output px
    cx = (p[0] - MAP["x0"]) * ppu + (sx - out_w / 2) * k
    cy = (p[1] - MAP["z0"]) * ppu + (sy - out_h / 2) * k
    box = (int(cx), int(cy), int(cx + sw * k), int(cy + sh * k))
    src, scaled = _styled if (_styled is not None and explored is not None) else _plain
    pre = scaled.get(round(k, 4))
    if pre is not None:                                      # fixed zoom: crop only
        x, y = int(round(cx / k)), int(round(cy / k))
        return _crop_fill(pre, (x, y, x + sw, y + sh), MAP["bg"])
    return _crop_fill(src, box, MAP["bg"]).resize((sw, sh), Image.BILINEAR)

def _paste(base, im, x, y):
    if im is not None:
        base.alpha_composite(im, (int(x - im.size[0] / 2), int(y - im.size[1] / 2)))

def render(p, heading, out_w, out_h, units_per_px, icon_px, pin_edges, sub=None):
    """Map art + explored shading + game icons + player. pin_edges: off-view icons (and the
    clamped objective) are pinned to the nearest edge of the square, pointing their way.
    sub=(x, y, w, h): render only that part of the view (fullscreen skips empty space)."""
    sx, sy = (sub or (0, 0))[:2]
    img = _background(p, out_w, out_h, units_per_px, sub).convert("RGBA")
    cx, cy = out_w / 2 - sx, out_h / 2 - sy
    hx, hy = out_w / 2 - icon_px * 0.5, out_h / 2 - icon_px * 0.5

    def to_edge(dx, dy):
        t = min(hx / abs(dx) if dx else 1e9, hy / abs(dy) if dy else 1e9)
        return cx + dx * t, cy + dy * t

    for key, d in remembered.items():
        if d.get("done") or style_for(d["img"]) is None:
            continue
        if key == "objective_dir":
            if pin_edges:
                _paste(img, icon(d["img"], int(icon_px * 0.8)), *to_edge(d["dirx"], d["diry"]))
            continue
        dx, dy = (d["x"] - p[0]) / units_per_px, (d["z"] - p[1]) / units_per_px
        if abs(dx) <= hx and abs(dy) <= hy:
            _paste(img, icon(d["img"], icon_px), cx + dx, cy + dy)
        elif pin_edges:
            _paste(img, icon(d["img"], int(icon_px * 0.7)), *to_edge(dx, dy))
    # player: the map's own player icon (art points down = +90 deg), rotated to the heading
    _paste(img, icon("mapiconplayer", int(icon_px * 1.15), (heading if heading is not None else 90) - 90), cx, cy)
    return img.convert("RGB")

# Native registered hotkey: no Python callback in the system keyboard input path.
import ctypes.wintypes as _wt
_toggle_req = threading.Event()
_toggle_t = [None]          # when the last toggle key arrived (debug latency only)

def _hook_thread():
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.RegisterHotKey.argtypes = [_wt.HWND, ctypes.c_int, _wt.UINT, _wt.UINT]
    u32.RegisterHotKey.restype = _wt.BOOL
    u32.UnregisterHotKey.argtypes = [_wt.HWND, ctypes.c_int]
    u32.PeekMessageW.argtypes = [ctypes.POINTER(_wt.MSG), _wt.HWND, _wt.UINT, _wt.UINT, _wt.UINT]
    u32.MsgWaitForMultipleObjects.argtypes = [_wt.DWORD, ctypes.c_void_p, _wt.BOOL, _wt.DWORD, _wt.DWORD]
    msg = _wt.MSG()
    registered = False
    fallback_down = False
    try:
        while True:
            focused = game_focused()
            if focused and not registered:
                # A hotkey only fires with exactly its modifiers, so register ` with every
                # Alt/Ctrl/Shift/Win combination (hover keeps Shift held, etc.).
                ok = [bool(u32.RegisterHotKey(None, 1 + m, 0x4000 | m, 0xC0)) for m in range(16)]
                registered = ok[0]
            elif not focused and registered:
                [u32.UnregisterHotKey(None, 1 + m) for m in range(16)]
                registered = False
            while u32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 1):
                if focused:
                    _toggle_t[0] = time.perf_counter(); _toggle_req.set()
            down = bool(u32.GetAsyncKeyState(0xC0) & 0x8000)
            if focused and not registered and down and not fallback_down:
                _toggle_t[0] = time.perf_counter(); _toggle_req.set()
            fallback_down = down
            u32.MsgWaitForMultipleObjects(0, None, False, 20, 0x0080)   # QS_HOTKEY wakes at once
    finally:
        if registered:
            [u32.UnregisterHotKey(None, 1 + m) for m in range(16)]

threading.Thread(target=_hook_thread, daemon=True).start()

def poll_toggle():
    global fullscreen, _last_render
    if _toggle_req.is_set():
        _toggle_req.clear()
        fullscreen = not fullscreen
        _last_render = None

MAP_BG = (12, 10, 40)

def _map_rect(p, w, h, upp, margin):
    """Screen rectangle (x, y, w, h) covered by the map texture (plus an icon margin)."""
    if MAP is None:
        return (0, 0, w, h)
    x0 = w / 2 + (_b["x_min"] - p[0]) / upp - margin; x1 = w / 2 + (_b["x_max"] - p[0]) / upp + margin
    y0 = h / 2 + (_b["z_min"] - p[1]) / upp - margin; y1 = h / 2 + (_b["z_max"] - p[1]) / upp + margin
    x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None

def minimap_center(w, h):
    # Keep the 16:9 horizontal anchor; clear the ammo/weapon XP HUD above it.
    safe_width = min(w, h * 16 / 9)
    safe_right = (w + safe_width) / 2
    top = min(180, max(12, h - SIZE - 12))
    return safe_right - SIZE / 2 - 60, SIZE / 2 + top


# --debug only: if the Tk thread stalls for 2 s, dump every thread's stack (Windows
# closes a window that stops pumping messages for ~5 s as "not responding").
_watchdog = None
if DEBUG:
    import faulthandler
    _watchdog = open("../research/minimap.hang.log", "a")

def draw(c, w, h):
    if _watchdog:
        faulthandler.dump_traceback_later(2.0, repeat=True, file=_watchdog)
    t = time.perf_counter()
    _draw(c, w, h)
    dt = time.perf_counter() - t
    if dt > 0.15:
        debug_log(f"slow frame {dt * 1000:.0f} ms (fullscreen={fullscreen})")
    if _last_render not in (None, "hidden", "status") and not _toggle_req.is_set():
        refresh_fog()               # after drawing, so a toggle frame never waits on it
    if _toggle_t[0] is not None and not _toggle_req.is_set():
        debug_log(f"toggle -> {'full' if fullscreen else 'mini'} drawn in {(time.perf_counter() - _toggle_t[0]) * 1000:.1f} ms")
        _toggle_t[0] = None


def _draw(c, w, h):
    global _view_photo, _last_render
    global _captured_this_open
    global _sprint_context
    poll_toggle()                   # first, so a wake-up redraw always consumes it
    sample = heroread.hero_sample()
    p = sample.xz if sample else None
    is_open = map_open()
    hidden_by = heroread.hide_state(sample)    # cutscene etc.: native hero state
    no_map = p is not None and not map_supported()   # map offline / planet without art
    # The fullscreen overlay is only a view: gameplay (and hover/sprint) carries on under it.
    _sprint_context = (time.monotonic(), p is not None and not is_open and not hidden_by)
    if not is_open:
        _captured_this_open = False
    if p and is_open:
        capture(p)
        if _last_render != "hidden":
            c.delete("all"); _last_render = "hidden"
        return                      # hide while the pause map is up
    if hidden_by or no_map:
        if _last_render != "hidden":
            c.delete("all"); _last_render = "hidden"
        return
    if not p or not game_focused():
        if p is None and game_focused():
            c.delete("all"); _last_render = "status"
            c.create_text(minimap_center(w, h)[0], 60, text=heroread.tracking_status(), fill="#cfd8ff", font=("Segoe UI", 12))
        elif _last_render != "hidden":
            c.delete("all"); _last_render = "hidden"
        return
    global _alpha_set
    if not _alpha_set:
        overlay.set_alpha(ALPHA); _alpha_set = True
    head = sample.heading + facing_offset
    n = sum(1 for k, d in remembered.items() if not d.get("done") and k != "objective_dir" and style_for(d["img"]))
    mode_label = sprint.mode_label
    state = ("full" if fullscreen else "mini", round(p[0], 1), round(p[1], 1), round(head or 0), n, mode_label)
    if fullscreen and state == _last_render:
        return                      # nothing changed - keep the big image (it is expensive)
    _last_render = state
    c.delete("all")
    if fullscreen:
        upp = full_height_world() / h
        c.create_rectangle(0, 0, w, h, fill="#%02x%02x%02x" % MAP_BG, outline="")
        sub = _map_rect(p, w, h, upp, margin=56)
        if sub:
            _view_photo = ImageTk.PhotoImage(render(p, head, w, h, upp, 56, pin_edges=False, sub=sub))
            c.create_image(sub[0], sub[1], image=_view_photo, anchor="nw")
        c.create_text(w / 2, h - 40, text=f"{n} marked  -  ` to close  -  {mode_label} (F8)  -  open the pause map to refresh",
                      fill="#ffffff", font=("Segoe UI", 16, "bold"))
        return
    r = SIZE / 2
    cx, cy = minimap_center(w, h)
    _view_photo = ImageTk.PhotoImage(render(p, head, SIZE, SIZE, radius_world() / r, 34, pin_edges=True))
    c.create_image(cx - r, cy - r, image=_view_photo, anchor="nw")
    c.create_rectangle(cx - r, cy - r, cx + r, cy + r, outline="#3a86ff", width=3)

_plain = (None, {})
if __name__ == "__main__":
    from sprint_assist import SprintAssist
    sprint = SprintAssist(read, EXE.lpBaseOfDll, pid, sprint_gameplay_allowed)
    sprint.start()
    try:
        overlay.run(draw, interval_ms=50, wake=_toggle_req)
    finally:
        sprint.close()


