# Benchmark the minimap's hero tracking: balanced moves (end where we started), sampling at
# 20 Hz. Checks: no jumps, agreement with independently verified copies, on explored ground.
import math, threading, time, numpy as np
import drive, heroread, fogread
from pos import reread

hero_copies = np.load("hero_copies.npy")
g = fogread.grid(dict(fogread.table())[0xbd52b112])

def explored(x, z):
    c, r = int((x + 192) / 2), int((z + 728) / 2)
    return bool(g[max(0, r - 2):r + 3, max(0, c - 2):c + 3].any())

def copies_median():
    v = reread(hero_copies); v = v[np.isfinite(v).all(1)]
    return np.median(v, 0)[[0, 2]] if len(v) else None

samples, stop = [], threading.Event()
def sampler():
    while not stop.is_set():
        samples.append((time.time(), heroread.hero_xz_filtered(), heroread.hero_heading()))
        time.sleep(0.05)

drive.focus(); time.sleep(0.6)
start = heroread.hero_xz()
th = threading.Thread(target=sampler, daemon=True); th.start()
report = []
for k in ["w", "s", "d", "a", "s", "w", "a", "d"]:
    if start and heroread.hero_xz() and math.dist(heroread.hero_xz(), start) > 12:
        report.append("safety stop: more than 12 units from start"); break
    drive.focus(); drive.hold(k, 1.0); time.sleep(0.5)
    p, c = heroread.hero_xz(), copies_median()
    report.append(f"after {k}: chains {None if p is None else (round(p[0], 1), round(p[1], 1))}  "
                  f"copies {None if c is None else (round(c[0], 1), round(c[1], 1))}  "
                  f"diff {math.dist(p, c) if p and c is not None else float('nan'):.2f}  "
                  f"explored {explored(*p) if p else None}")
stop.set(); th.join()
end = heroread.hero_xz()
pts = [s for s in samples if s[1] is not None]
jumps = [math.dist(a[1], b[1]) for a, b in zip(pts, pts[1:])]
speeds = [math.dist(a[1], b[1]) / max(1e-3, b[0] - a[0]) for a, b in zip(pts, pts[1:])]
gaps = [b[0] - a[0] for a, b in zip(pts, pts[1:])]
print("\n".join(report))
print(f"samples {len(samples)}  missing {len(samples) - len(pts)}  "
      f"max jump between samples {max(jumps):.2f} units  (sprinting ~0.6/sample)")
print(f"max speed {max(speeds):.1f} units/s (walking ~6-8)   longest gap between samples {max(gaps):.2f} s")
print(f"headings read {sum(1 for s in samples if s[2] is not None)}/{len(samples)}")
print(f"drift from start {math.dist(start, end):.2f} units")


