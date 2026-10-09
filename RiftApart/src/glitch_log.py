# Passive capture while the user plays: native sprint toggle/mode, hero and weapon
# states, mouse/keys, and every assist action, every ~3 ms. Sends no input itself
# (the in-process SprintAssist does, exactly as minimap.py would).
# Usage: python glitch_log.py [seconds] [always|normal|off]
import sys, time, json, ctypes, threading
import mem, pymem
import runtime_config
from comp_dump import names
import sprint_assist

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 180
mode = sys.argv[2] if len(sys.argv) > 2 else "always"
u32 = ctypes.windll.user32
held = lambda vk: bool(u32.GetAsyncKeyState(vk) & 0x8000)
pid = pymem.Pymem("RiftApart.exe").process_id
t0 = time.monotonic()
events = []
runtime_config.DEBUG = True
sprint_assist.debug_log = lambda *a, **k: events.append((round(time.monotonic() - t0, 4), " ".join(map(str, a))))
assist = None
if mode != "off":
    sprint_assist.load_mode = lambda path=None: mode
    sprint_assist.save_mode = lambda m, path=None: None
    assist = sprint_assist.SprintAssist(mem.read, mem.EXE.lpBaseOfDll, pid, lambda: True)
reader = sprint_assist.SprintReader(mem.read, mem.EXE.lpBaseOfDll)
out = open("glitch_log.jsonl", "w")
last_mo = None
if assist:
    assist.start()
print(f"logging {seconds:.0f}s, assist={mode}", flush=True)
try:
    while time.monotonic() - t0 < seconds:
        n = names() or {}
        st = sorted({v[0].split("@")[0][8:].replace("State", "") for v in n.values()
                     if ("HeroState" in v[0] or "HeroWeaponState" in v[0]) and "Local" not in v[0]})
        ws = sorted({x.replace("Weapon", "W") for x in st if x.startswith("Weapon")})
        st = [x for x in st if not x.startswith("Weapon")]
        h = reader.hero.sample()
        tog = modev = None
        if h:
            res = reader.component(h.entity)
            if res:
                tb = mem.read(res[0] + 0x1CF, 1); tog = tb[0] if tb else None
                pc = mem.u64(res[0] + 0x108); mo = mem.u64(pc + 0x158) if pc else None
                if mo: last_mo = mo
        if last_mo:
            mb = mem.read(last_mo + 0xA8, 2); modev = mb[0] if mb else None
        foc = ctypes.c_ulong(); u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), ctypes.byref(foc))
        out.write(json.dumps([round(time.monotonic() - t0, 4), int(held(1)), int(held(2)), int(held(0x10)),
                              "".join(k for k, vk in zip("wasd", (0x57, 0x41, 0x53, 0x44)) if held(vk)),
                              ",".join(st), ",".join(ws), tog, modev, int(foc.value == pid)]) + "\n")
        time.sleep(0.003)
finally:
    if assist:
        assist.close()
    out.close()
    json.dump(events, open("glitch_events.json", "w"))
    print("done", flush=True)
