# Find the player's position by narrowing candidates between movement rounds.
# Candidates: 16-byte aligned float4 (x, y, z, w) with w == 0 or 1 and plausible xyz.
#   python pos.py snap     # stand still, take the first snapshot
#   python pos.py moved    # after moving: keep candidates that changed
#   python pos.py still    # after standing still: keep candidates that did not change
#   python pos.py show     # list survivors (current values)
import sys, time, numpy as np
from mem import regions, read

STATE = "pos_state.npz"
LIM = 100000.0

def scan_all():
    addrs, vals = [], []
    for base, size in regions():
        b = read(base, size)
        if not b or len(b) < 16:
            continue
        n = len(b) // 16
        f = np.frombuffer(b[: n * 16], np.float32).reshape(n, 4)
        with np.errstate(invalid="ignore"):
            xyz = f[:, :3]
            ok = (((f[:, 3] == 1.0) | (f[:, 3] == 0.0)) & np.isfinite(xyz).all(1)
                  & (np.abs(xyz) < LIM).all(1) & (np.abs(xyz).max(1) > 1.0)
                  & (np.abs(xyz) > 1e-6).all(1))
        idx = np.nonzero(ok)[0]
        if len(idx):
            addrs.append(base + idx.astype(np.uint64) * 16)
            vals.append(xyz[idx].copy())
    return np.concatenate(addrs), np.concatenate(vals)

def reread(addrs):
    out = np.full((len(addrs), 3), np.nan, np.float32)
    order = np.argsort(addrs)
    a = addrs[order]
    for base, size in regions():
        lo, hi = np.searchsorted(a, [base, base + size])
        if lo == hi:
            continue
        b = read(base, size)
        if not b:
            continue
        f = np.frombuffer(b[: len(b) // 4 * 4], np.float32)
        off = ((a[lo:hi] - base) // 4).astype(np.int64)
        out[order[lo:hi]] = np.stack([f[off], f[off + 1], f[off + 2]], 1)
    return out

def save(a, v): np.savez(STATE, a=a, v=v)
def load(): d = np.load(STATE); return d["a"], d["v"]

if __name__ == "__main__":
    cmd = sys.argv[1]
    t = time.time()
    if cmd == "snap":
        a, v = scan_all()
    else:
        a, v = load()
        if cmd in ("moved", "still"):
            nv = reread(a)
            d = np.abs(nv - v).max(1)
            keep = (d > 0.5) if cmd == "moved" else (d < 1e-3)
            keep &= np.isfinite(nv).all(1)
            a, v = a[keep], nv[keep]
        elif cmd == "show":
            v = reread(a)
            for i in range(min(len(a), int(sys.argv[2]) if len(sys.argv) > 2 else 40)):
                print(f"{int(a[i]):#x}  {v[i][0]:10.2f} {v[i][1]:10.2f} {v[i][2]:10.2f}")
    save(a, v)
    print(f"{cmd}: {len(a):,} candidates ({time.time() - t:.1f}s)")
