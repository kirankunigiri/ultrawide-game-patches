# Track which HeroState* components exist while driving short balanced inputs.
import sys, time, threading, math, os
LIMIT = float(os.environ.get('PROBE_LIMIT', 12))
import mem, drive
from comp_dump import names
from sprint_assist import SprintReader
import runtime_config; runtime_config.DEBUG = True
ASSIST = os.environ.get("ASSIST")
allowed = [True]
if ASSIST:
    import pymem, sprint_assist
    sprint_assist.load_mode = lambda path=None: ASSIST
    a = sprint_assist.SprintAssist(mem.read, mem.EXE.lpBaseOfDll, pymem.Pymem("RiftApart.exe").process_id, lambda: allowed[0])
import ctypes
def mouse(btn, down):
    flags = {("l", True): 2, ("l", False): 4, ("r", True): 8, ("r", False): 16}[(btn, down)]
    ctypes.windll.user32.mouse_event(flags, 0, 0, 0, 0)
drive.SC.update({"shift": 0x2A, "space": 0x39, "ctrl": 0x1D, "alt": 0x38})
r = SprintReader(mem.read, mem.EXE.lpBaseOfDll)
print("focused", drive.focus()); time.sleep(1.0)
x0, z0 = r.hero.sample().xz
print("start", x0, z0)
log, stop, held = [], threading.Event(), set()
last_mo = None
def samp():
    t0 = time.monotonic()
    while not stop.is_set():
        n = names() or {}
        st = sorted({v[0].split('@')[0][4:] for v in n.values() if 'HeroState' in v[0] and 'Weapon' not in v[0]})
        s = r.sample(); h = r.hero.sample()
        mode = None
        global last_mo
        if last_mo:
            mb = mem.read(last_mo + 0xA8, 2); mode = mb[0] if mb else None
        if h:
            res = r.component(h.entity)
            if res:
                pc = mem.u64(res[0] + 0x108); mo = mem.u64(pc + 0x158) if pc else None
                if mo: last_mo = mo; mb = mem.read(mo + 0xA8, 2); mode = mb[0] if mb else None
        wst = ",".join(sorted({v[0].split('@')[0][4:].replace('HeroWeaponState', 'W') for v in n.values() if 'WeaponState' in v[0] and 'Local' not in v[0]}))
        d = math.hypot(h.xz[0]-x0, h.xz[1]-z0) if h else -1
        log.append((round(time.monotonic()-t0, 3), ",".join(st), None if s is None else int(s.sprinting), round(d, 1), "+".join(sorted(held)), mode, wst))
        if d > LIMIT:
            for k in list(held): mouse(k[0], False) if k in ('lmb', 'rmb') else drive._key(drive.SC[k], True)
            held.clear(); log.append(("SAFETY", d)); stop.set()
        time.sleep(0.002)
th = threading.Thread(target=samp, daemon=True); th.start()
if ASSIST: a.start()
try:
    for ev in sys.argv[1:]:                     # +w down, -w up, ^shift tap, 0.5 sleep
        if stop.is_set(): break
        if ev in ("+lmb", "+rmb", "-lmb", "-rmb"):
            mouse(ev[1], ev[0] == "+"); (held.add if ev[0] == "+" else held.discard)(ev[1:])
        elif ev[0] == "+": held.add(ev[1:]); drive._key(drive.SC[ev[1:]], False)
        elif ev[0] == "-": held.discard(ev[1:]); drive._key(drive.SC[ev[1:]], True)
        elif ev[0] == "^": drive._key(drive.SC[ev[1:]], False); time.sleep(0.08); drive._key(drive.SC[ev[1:]], True)
        elif ev.startswith("home:"):
            allowed[0] = False; time.sleep(0.6); k = ev[5:]; held.add(k); drive._key(drive.SC[k], False); best = 1e9; t1 = time.monotonic()
            while time.monotonic() - t1 < 6:
                p = r.hero.sample().xz; cur = math.hypot(p[0]-x0, p[1]-z0)
                if cur < 0.4 or cur > best + 0.5: break
                best = min(best, cur); time.sleep(0.01)
            held.discard(k); drive._key(drive.SC[k], True)
        else: time.sleep(float(ev))
finally:
    for k in list(held): mouse(k[0], False) if k in ('lmb', 'rmb') else drive._key(drive.SC[k], True)
    time.sleep(0.5); stop.set(); th.join()
    if ASSIST: a.close()
prev = None
for row in (log if not os.environ.get('QUIET') else []):
    if len(row) < 5 or row[1:3] + row[4:] != prev: print(row); prev = row[1:3] + row[4:] if len(row) >= 5 else None
import json; json.dump(log, open("state_probe_log.json", "w"))
h = r.hero.sample(); print("drift", round(math.hypot(h.xz[0]-x0, h.xz[1]-z0), 2))
