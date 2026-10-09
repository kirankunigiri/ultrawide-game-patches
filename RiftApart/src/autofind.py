# Automated hero-position finder: drive the hero with WASD and keep only memory copies that
# move by exactly the hero's displacement every time (and stay put while idle).
import collections, time, numpy as np
import drive
from pos import scan_all, reread

def dominant_shift(before, after):
    d = after - before
    moved = np.isfinite(d).all(1) & (np.hypot(d[:, 0], d[:, 2]) > 3.0)   # a 1.2 s walk moves several units
    keys = collections.Counter(map(tuple, np.round(d[moved][:, [0, 2]] / 0.25).astype(int)))
    (kx, kz), n = keys.most_common(1)[0]
    return np.array([kx, kz]) * 0.25, n

def run(moves=("w", "d", "s", "a", "w"), seconds=1.2, log=print):
    drive.focus(); time.sleep(0.6)
    a, v = scan_all()
    log(f"start: {len(a):,} candidates")
    for k in moves:
        before = reread(a)
        drive.focus(); drive.hold(k, seconds); time.sleep(0.5)
        after = reread(a)
        shift, n = dominant_shift(before, after)
        d = (after - before)[:, [0, 2]]
        keep = np.isfinite(d).all(1) & (np.abs(d - shift).max(1) < 0.3)
        a, v = a[keep], after[keep]
        log(f"move {k}: hero shift ({shift[0]:+.2f}, {shift[1]:+.2f}) -> {len(a):,} copies left")
        # idle check: copies must hold still while the hero stands
        time.sleep(0.8)
        idle = reread(a)
        keep = np.isfinite(idle).all(1) & (np.abs(idle - v).max(1) < 0.05)
        a, v = a[keep], idle[keep]
        log(f"   idle: {len(a):,} copies left")
    return a, v

if __name__ == "__main__":
    a, v = run()
    np.save("hero_copies.npy", a)
    print("hero at", np.median(v, 0), "copies", len(a))
    for x in a[:10]:
        print(hex(int(x)))

