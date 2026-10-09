# Walk the hero back to a point with short taps (no sprint/hover), testing directions.
import sys, time, math, json, mem, drive
from player_tracking import HeroReader
h = HeroReader(mem.read, mem.EXE.lpBaseOfDll)
tx, tz = json.load(open("_start.json"))
d = lambda: math.hypot(h.sample().xz[0]-tx, h.sample().xz[1]-tz)
drive.focus(); time.sleep(0.6)
from sprint_assist import SprintReader
_r = SprintReader(mem.read, mem.EXE.lpBaseOfDll)
_s = _r.sample()
if _s and _s.sprinting:                       # hover/sprint on: switch it off before walking
    drive._key(0x2A, False); time.sleep(0.08); drive._key(0x2A, True); time.sleep(1.0)
opp = {"w": "s", "s": "w", "a": "d", "d": "a"}
for step in range(40):
    cur = d()
    if cur < 0.8: break
    best = None
    for key in ("w", "s", "a", "d"):
        drive.hold(key, 0.12); time.sleep(0.35)
        if d() < cur - 0.05: best = key; break
        drive.hold(opp[key], 0.12); time.sleep(0.35)
    if best is None: break
    while True:
        before = d(); drive.hold(best, 0.25); time.sleep(0.35)
        if d() > before - 0.05 or d() < 0.8: break
print("end dist", round(d(), 2))
