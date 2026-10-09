# Read-only: log hero state class names whenever they change (every ~0.1 s), to find
# which native state a screen (store, cutscene, ...) puts the hero in.
import sys, time, json
from comp_dump import names
seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 300
t0 = time.monotonic(); prev = None
out = open("state_watch.log", "w")
while time.monotonic() - t0 < seconds:
    n = names() or {}
    st = sorted({v[0].split("@")[0][8:] for v in n.values() if "HeroState" in v[0] and "Weapon" not in v[0]})
    if st != prev:
        out.write(f"{time.monotonic() - t0:7.2f} {time.strftime('%H:%M:%S')} {','.join(st)}\n"); out.flush()
        prev = st
    time.sleep(0.1)
