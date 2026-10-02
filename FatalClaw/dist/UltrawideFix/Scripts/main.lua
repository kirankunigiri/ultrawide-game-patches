-- UltrawideFix 1.0 - Fatal Claw ultrawide (21:9 / 32:9) fix
-- UE4SS Lua mod for Unreal Engine 4.27. Settings live in config.lua next to this file.
-- Full write-up: FatalClaw/notes.md in https://github.com/kirankunigiri/ultrawide-game-patches
--
-- Silent by default: nothing is logged unless Debug = true in config.lua (then it writes
-- what it does to ue4ss\UE4SS.log). If config.lua can't be read, it stays silent too.
--
-- WHAT IT DOES
-- 1. 16:9 lock: the game sets bConstrainAspectRatio = true on its cameras, which pillarboxes
--    the image. Cleared on every camera so the view fills the screen.
-- 2. FOV (Hor+): CameraComponent.FieldOfView is the HORIZONTAL fov in UE, so without the lock
--    the game looks zoomed in on a wider screen (~2x at 32:9). Every FOV is widened so the
--    VERTICAL view matches 16:9 and the extra width shows more of the world:
--        fov' = 2 * atan( tan(fov / 2) * (screenAspect / (16/9)) )
--    e.g. gameplay 60 -> 98.2 deg at 32:9, 60 -> 75.6 deg at 3440x1440.
-- 3. Axis constraint: LocalPlayer forced to MaintainXFOV so the math is deterministic.
-- 4. Tint overlay: BP_FCHeroCamera carries a darkening sprite (LayerSpriteComponent) 200u in
--    front of the lens, sized for the 16:9 view. Camera-attached sprites are widened by the
--    same factor the visible width grew.
-- 5. Per-frame FOV: cutscenes, the title intro and the gate-teleport zoom (60 -> 40 -> 11 on
--    entry and back out on exit) set FOV every frame through CameraComponent:SetFieldOfView.
--    A post-hook converts every call; a 250ms loop on the game thread is the fallback for
--    direct property writes (a Blueprint SET node never goes through the setter).
-- 6. Never converting twice: a value the game reads back and re-sets (e.g. a cutscene
--    restoring the FOV it captured before it started) is already converted and is left
--    alone. Only values this mod really wrote are recognised, by EXACT float match: the
--    last few written to that camera, plus "resting" values (ours and still in place at a
--    loop tick). Both lists are small and fixed-size.
--
-- LESSONS (each one cost a crash or a regression - details in notes.md)
-- * Gate flicker: "already converted?" used to compare values ROUNDED to 0.01 against
--   EVERY value ever written. Raw frames of the gate zoom kept matching old converted
--   values and were skipped (rendered zoomed in), worse with every teleport as the list
--   grew. Exact matching against a small per-camera window fixed it.
-- * Run the loop on the game thread (LoopInGameThreadWithDelay). LoopAsync +
--   ExecuteInGameThread raced the game-thread hook: UE4SS died with "Ref was not function".
-- * Never call ExecuteWithDelay / ExecuteInGameThread from inside a hook callback. Hooks
--   only read/write properties; anything else is queued for the loop.
-- * Leave alone: Level Sequence spawnable TEMPLATES (objects inside the sequence asset), the
--   SceneCaptureComponent2Ds (they render only the hero into RT_Hero for warp effects -
--   changing them shrinks or hides the hero) and the camera manager's AnimCameraActor (a
--   camera-anim driver, not a view).

local MOD_NAME = "UltrawideFix"
local VERSION  = "1.0"

local BASE_ASPECT     = 16.0 / 9.0       -- aspect the game was designed for
local AXIS_MAINTAIN_X = 1                -- EAspectRatioAxisConstraint::AspectRatio_MaintainXFOV
local RECENT_MAX      = 8                -- per camera: last values written that count as ours
local RESTING_MAX     = 16               -- per camera: resting values remembered

-------------------------------------------------------------------------------
-- helpers
-------------------------------------------------------------------------------
local DEBUG = false       -- set from config.lua (Debug = true) once it has been read

local function log(msg)
    if not DEBUG then return end
    print("[" .. MOD_NAME .. "] " .. tostring(msg) .. "\n")
end

local function safe(f, default)
    local ok, v = pcall(f)
    if ok then return v end
    return default
end

-------------------------------------------------------------------------------
-- settings (config.lua next to this file)
-------------------------------------------------------------------------------
local DEFAULTS = { ScreenWidth = 5120, ScreenHeight = 1440, FovScale = 1.0, Debug = false }

local function loadConfig()
    -- load by path, so nothing else on package.path can shadow a file named config.lua
    local src = safe(function() return debug.getinfo(1, "S").source end, "") or ""
    local dir = src:match("^@(.*[\\/])")
    if dir then
        local path = dir .. "config.lua"
        local chunk, err = loadfile(path)
        if not chunk then return nil, err end
        local ok, res = pcall(chunk)
        if ok and type(res) == "table" then return res, path end
        return nil, "config.lua did not return a table (" .. tostring(res) .. ")"
    end
    local ok, res = pcall(require, "config")
    if ok and type(res) == "table" then return res, "require('config')" end
    return nil, tostring(res)
end

local cfg, cfgFrom = loadConfig()
local cfgError = nil
if not cfg then
    cfgError = tostring(cfgFrom)
    cfg, cfgFrom = {}, "defaults"
end
DEBUG = cfg.Debug == true
if cfgError then log("WARNING: could not load config.lua (" .. cfgError .. ") - using 5120x1440") end

local function setting(key, lo, hi)
    local v = cfg[key]
    if type(v) == "number" and v == v and v >= lo and v <= hi then return v end
    if v ~= nil then
        log(string.format("WARNING: config %s = %s is invalid, using %s", key, tostring(v), tostring(DEFAULTS[key])))
    end
    return DEFAULTS[key]
end

local SCREEN_W      = setting("ScreenWidth", 320, 32768)
local SCREEN_H      = setting("ScreenHeight", 200, 32768)
local FOV_SCALE     = setting("FovScale", 0.5, 2.0)
local TARGET_ASPECT = SCREEN_W / SCREEN_H

log(string.format("%s %s: screen %.0fx%.0f (aspect %.4f, game designed for %.4f), FOV scale %.2f - settings from %s",
    MOD_NAME, VERSION, SCREEN_W, SCREEN_H, TARGET_ASPECT, BASE_ASPECT, FOV_SCALE, cfgFrom))

if TARGET_ASPECT <= BASE_ASPECT + 0.01 then
    log("screen is not wider than 16:9 - nothing to fix, mod inactive")
    return
end

-------------------------------------------------------------------------------
-- math / naming
-------------------------------------------------------------------------------
local function fullName(obj)
    if obj == nil then return "nil" end
    return safe(function() return obj:GetFullName() end, "?")
end

local function className(obj)
    return safe(function() return obj:GetClass():GetFName():ToString() end, "?")
end

local function isTemplate(name)
    return name:find(":MovieScene", 1, true) ~= nil or name:find("Default__", 1, true) ~= nil
end

local function isCine(cam)
    return className(cam):find("CineCamera", 1, true) ~= nil
end

local function horPlus(hfov)
    local half = math.rad(hfov) / 2
    local t = math.tan(half) * (TARGET_ASPECT / BASE_ASPECT)
    local out = math.deg(2 * math.atan(t)) * FOV_SCALE
    if out > 170 then out = 170 end
    return out
end

-- how much wider the visible area is at a fixed distance in front of the camera
local function widthRatio(origFov)
    if origFov == nil then return TARGET_ASPECT / BASE_ASPECT end
    return math.tan(math.rad(horPlus(origFov)) / 2) / math.tan(math.rad(origFov) / 2)
end

-- Exact key for a float property value. Values are always READ BACK from the float32
-- property before being keyed, so equal floats give equal keys and nothing else does.
local function fkey(v) return string.format("%.9g", v) end

-------------------------------------------------------------------------------
-- state
-------------------------------------------------------------------------------
local recentRing = {}     -- camera fullName -> array of keys we wrote (oldest first)
local recentSet = {}      -- camera fullName -> key -> count (lookup for recentRing)
local resting = {}        -- camera fullName -> { keys = {key -> true}, n = count }
local camOrigFov = {}     -- camera fullName -> last FOV the game set (pre-conversion)
local convertCount = {}   -- camera fullName -> number of conversions
local seenCams = {}       -- camera fullName -> true (sprite discovery done)
local spriteState = {}    -- sprite fullName -> { comp, axis, cam, mine }
local cineDone = {}       -- cine camera fullName -> sensor width we wrote
local pendingSight = {}   -- camera fullName -> camera (queued by the hook for the loop)
local rediscover = {}     -- camera fullName -> { cam, at }
local excludedActors = {} -- actor fullName -> true (camera-anim drivers; never convert)
local loggedPlayer = false
local stats = { setter = 0, loop = 0, readback = 0 }
local lastBeat = 0

-- remember a value we just wrote (v must be read back from the property)
local function remember(name, v)
    local k = fkey(v)
    local ring, set = recentRing[name], recentSet[name]
    if not ring then
        ring, set = {}, {}
        recentRing[name], recentSet[name] = ring, set
    end
    ring[#ring + 1] = k
    set[k] = (set[k] or 0) + 1
    if #ring > RECENT_MAX then
        local old = table.remove(ring, 1)
        local c = set[old] - 1
        set[old] = (c > 0) and c or nil
    end
end

local function isOurs(name, v)
    local k = fkey(v)
    local s = recentSet[name]
    if s and s[k] then return true end
    local r = resting[name]
    return r ~= nil and r.keys[k] == true
end

-- loop only: a value of ours still sitting on the camera is a resting value. Cutscenes
-- capture these as pre-animated state and restore them much later, after the recent
-- window has rolled over, so they are remembered separately.
local function noteResting(name, v)
    local k = fkey(v)
    local s = recentSet[name]
    if not (s and s[k]) then return end
    local r = resting[name]
    if not r then
        r = { keys = {}, n = 0 }
        resting[name] = r
    end
    if r.keys[k] then return end
    if r.n >= RESTING_MAX then r.keys, r.n = {}, 0 end
    r.keys[k] = true
    r.n = r.n + 1
end

-------------------------------------------------------------------------------
-- FOV conversion (property read/write only - safe inside hooks)
-- returns "converted", "ours" (already converted, left alone) or nil (not handled)
-------------------------------------------------------------------------------
local function ownerName(cam)
    return safe(function() return cam:GetOuter():GetFullName() end, "?")
end

local function applyFov(cam)
    local name = cam:GetFullName()
    if isTemplate(name) or isCine(cam) then return nil end
    if excludedActors[ownerName(cam)] then return nil end
    local cur = cam.FieldOfView
    if isOurs(name, cur) then return "ours" end

    cam.FieldOfView = horPlus(cur)
    local written = cam.FieldOfView        -- float32-rounded, exactly what the game will see
    remember(name, written)
    camOrigFov[name] = cur
    convertCount[name] = (convertCount[name] or 0) + 1
    local n = convertCount[name]
    if n <= 2 then
        log(string.format("FOV %.2f -> %.2f on %s", cur, written, name))
    elseif n == 3 then
        log("game keeps setting FOV on " .. name .. " (converting every change silently)")
    end
    return "converted"
end

-------------------------------------------------------------------------------
-- camera-attached tint sprites
-------------------------------------------------------------------------------
-- A Paper2D sprite lies in its local X/Z plane; pick the local axis that ends up
-- pointing sideways (camera +/-Y) after the sprite's relative rotation.
local function horizontalAxis(rot)
    local p, y = math.rad(rot.Pitch), math.rad(rot.Yaw)
    if math.abs(math.cos(p) * math.sin(y)) > 0.7 then return "X" end
    return "Z"
end

local function discoverSprites(cam)
    local camName = fullName(cam)
    local sprites = safe(function() return FindAllOf("PaperSpriteComponent") end, nil)
    if not sprites then return end
    for _, c in ipairs(sprites) do
        pcall(function()
            local sn = fullName(c)
            if spriteState[sn] or isTemplate(sn) then return end
            if fullName(c.AttachParent) ~= camName then return end
            local rot = c.RelativeRotation
            local axis = horizontalAxis(rot)
            spriteState[sn] = { comp = c, axis = axis, cam = camName, mine = nil }
            log(string.format("found camera tint sprite %s  rot=(P%.1f Y%.1f R%.1f) -> widening local %s",
                sn, rot.Pitch, rot.Yaw, rot.Roll, axis))
        end)
    end
end

local function fixSprites()
    for sn, st in pairs(spriteState) do
        pcall(function()
            local c = st.comp
            if not c:IsValid() then spriteState[sn] = nil; return end
            local s = c.RelativeScale3D
            local sx, sy, sz = s.X, s.Y, s.Z
            local cur = (st.axis == "X") and sx or sz
            if st.mine ~= nil and math.abs(cur - st.mine) <= 1e-4 then return end
            local target = cur * widthRatio(camOrigFov[st.cam])
            if st.axis == "X" then sx = target else sz = target end
            c:SetRelativeScale3D({ X = sx, Y = sy, Z = sz })
            st.mine = target
            log(string.format("widened tint sprite %s: %s %.3f -> %.3f", sn, st.axis, cur, target))
        end)
    end
end

-- new cameras: discover sprites now and once more ~2s later (the Blueprint may attach its
-- sprite a moment after spawning). Driven from the loop only.
local function firstSight(cam)
    local name = fullName(cam)
    if seenCams[name] or isTemplate(name) then return end
    seenCams[name] = true
    discoverSprites(cam)
    rediscover[name] = { cam = cam, at = os.time() + 2 }
end

local function processSightQueues()
    for name, cam in pairs(pendingSight) do
        pendingSight[name] = nil
        pcall(function() if cam:IsValid() then firstSight(cam) end end)
    end
    local now = os.time()
    for name, r in pairs(rediscover) do
        if now >= r.at then
            rediscover[name] = nil
            pcall(function() if r.cam:IsValid() then discoverSprites(r.cam) end end)
        end
    end
end

-- Cine cameras recompute FieldOfView from focal length + sensor width every tick, so their
-- sensor is widened instead (same Hor+ change). Defensive: this game has no cine cameras.
local function fixCine(cam)
    local name = fullName(cam)
    if isTemplate(name) then return end
    pcall(function()
        local fb = safe(function() return cam.Filmback end, nil) or safe(function() return cam.FilmbackSettings end, nil)
        if not fb then return end
        local w = fb.SensorWidth
        local mine = cineDone[name]
        if mine ~= nil and math.abs(w - mine) <= 1e-3 then return end
        local target = w * (TARGET_ASPECT / BASE_ASPECT) * FOV_SCALE
        fb.SensorWidth = target
        cineDone[name] = target
        log(string.format("cine camera %s: sensor width %.2f -> %.2f", name, w, target))
    end)
end

-------------------------------------------------------------------------------
-- hook (property read/write only; new cameras are queued for the loop)
-------------------------------------------------------------------------------
local function queueIfNew(cam)
    local name = cam:GetFullName()
    if not seenCams[name] and not isTemplate(name) then pendingSight[name] = cam end
end

local function noop() end

-- setter-driven FOV changes (cutscenes, title intro, gate zoom)
local function onSetFovPost(ctx)
    pcall(function()
        local cam = ctx:get()
        if cam and cam:IsValid() then
            local r = applyFov(cam)
            if r == "converted" then
                stats.setter = stats.setter + 1
            elseif r == "ours" then
                stats.readback = stats.readback + 1
            end
            queueIfNew(cam)
        end
    end)
end

do
    local fn = "/Script/Engine.CameraComponent:SetFieldOfView"
    local ok, err = pcall(function() RegisterHook(fn, noop, onSetFovPost) end)
    log((ok and "hooked " or "could NOT hook ") .. fn .. (ok and "" or (" (" .. tostring(err) .. ")")))
end

-------------------------------------------------------------------------------
-- Camera-anim driver exclusion: PlayerCameraManager.AnimCameraActor is the hidden camera
-- that camera animations write their FOV into; never convert it. Runs BEFORE fixCameras.
-------------------------------------------------------------------------------
local function excludeAnimCameras()
    local mgrs = safe(function() return FindAllOf("PlayerCameraManager") end, nil)
    if not mgrs then return end
    for _, pcm in ipairs(mgrs) do
        pcall(function()
            if not pcm:IsValid() then return end
            local a = pcm.AnimCameraActor
            if not a or not a:IsValid() then return end
            local an = a:GetFullName()
            if excludedActors[an] then return end
            excludedActors[an] = true
            log("excluding camera-anim driver " .. an)
        end)
    end
end

-------------------------------------------------------------------------------
-- main loop: constraint clearing, fallback FOV, sprites
-------------------------------------------------------------------------------
local function fixLocalPlayers()
    local players = FindAllOf("LocalPlayer")
    if not players then return end
    for _, lp in ipairs(players) do
        pcall(function()
            if not lp:IsValid() then return end
            local cur = lp.AspectRatioAxisConstraint
            if not loggedPlayer then
                log("LocalPlayer axis constraint was " .. tostring(cur))
                loggedPlayer = true
            end
            if cur ~= AXIS_MAINTAIN_X then lp.AspectRatioAxisConstraint = AXIS_MAINTAIN_X end
        end)
    end
end

local function handleCamera(cam)
    pcall(function()
        if not cam:IsValid() then return end
        local name = cam:GetFullName()
        if isTemplate(name) then return end
        if cam.bConstrainAspectRatio == true then
            cam.bConstrainAspectRatio = false
            log("cleared 16:9 lock on " .. name)
        end
        if isCine(cam) then
            fixCine(cam)
        else
            if applyFov(cam) == "converted" then stats.loop = stats.loop + 1 end
            noteResting(name, cam.FieldOfView)
        end
        firstSight(cam)
    end)
end

local function fixCameras()
    local cams = FindAllOf("CameraComponent")
    if cams then for _, cam in ipairs(cams) do handleCamera(cam) end end
    local cines = FindAllOf("CineCameraComponent")
    if cines then for _, cam in ipairs(cines) do handleCamera(cam) end end
end

local function tick()
    pcall(fixLocalPlayers)
    pcall(excludeAnimCameras)
    pcall(fixCameras)
    pcall(processSightQueues)
    pcall(fixSprites)
    local now = os.time()
    if DEBUG and now - lastBeat >= 60 then
        lastBeat = now
        local n = 0
        for _ in pairs(seenCams) do n = n + 1 end
        log(string.format("alive: %d cameras; FOV conversions %d by setter, %d by loop; %d re-sets of an already-converted value left alone",
            n, stats.setter, stats.loop, stats.readback))
    end
end

if LoopInGameThreadWithDelay then
    LoopInGameThreadWithDelay(250, tick)
    log("main loop: game thread")
else
    LoopAsync(250, function() ExecuteInGameThread(tick); return false end)
    log("main loop: async fallback (older UE4SS)")
end
