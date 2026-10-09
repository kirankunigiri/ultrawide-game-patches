# Re-find the hero position (and upright root transforms for facing) without user input:
# the hero position is the float4 (x, y, z, 0|1) value with by far the most copies in memory
# (root, bones, physics, camera target...), and it must lie inside the current map's bounds.
import json, struct, collections, numpy as np
from pos import scan_all
from mem import read

def find(bounds, min_copies=50, explored_at=None):
    a, v = scan_all()
    x0, z0, x1, z1 = bounds
    inside = (np.hypot(v[:, 0], v[:, 2]) > 5) & (v[:, 0] > x0) & (v[:, 0] < x1) & (v[:, 2] > z0) & (v[:, 2] < z1)
    a, v = a[inside], v[inside]
    if not len(v):
        return None
    keys = np.round(v / 0.5).astype(np.int64)
    c = collections.Counter(map(tuple, keys))

    def upright_roots(addrs):
        # upright root transforms: 3 orthonormal rows in front of the position, middle row = up
        roots = []
        for ad in addrs:
            b = read(int(ad) - 48, 64)
            if not b:
                continue
            m = np.array(struct.unpack("<16f", b)).reshape(4, 4)
            R = m[:3, :3]
            if np.isfinite(R).all() and m[1, 1] > 0.999 and np.allclose(R @ R.T, np.eye(3), atol=1e-3):
                roots.append(int(ad))
        return roots

    # The hero = a heavily copied position that also has upright root transforms (constants
    # and vectors that merely repeat don't). Rank the most-copied clusters by root count.
    best = None
    for (kx, ky, kz), n in c.most_common(80):
        if n < min_copies:
            break
        center = np.array([kx, ky, kz]) * 0.5
        # the hero always stands on explored ground (being there reveals it)
        if explored_at is not None and not explored_at(center[0], center[2]):
            continue
        addrs = a[np.abs(v - center).max(1) < 1.0]
        roots = upright_roots(addrs[:3000])
        if best is None or len(roots) > len(best[2]):
            best = (center, addrs, roots, n)
    if best is None or len(best[2]) < 3:
        return None
    center, addrs, roots, n = best
    pick = addrs[:: max(1, len(addrs) // 24)][:24]
    return dict(pos=center.tolist(), copies=int(n), fast=[int(x) for x in pick], roots=roots)

if __name__ == "__main__":
    import time
    t = time.time()
    import fogread
    g = fogread.grid(dict(fogread.table())[0xbd52b112])
    def explored_at(x, z):
        c, r = int((x + 192) / 2), int((z + 728) / 2)
        return 0 <= r < g.shape[0] and 0 <= c < g.shape[1] and g[max(0, r - 3):r + 4, max(0, c - 3):c + 4].any()
    r = find((-192, -728, 920, 384), explored_at=explored_at)
    print(f"{time.time() - t:.1f}s", None if r is None else
          f"player {r['pos']}  copies {r['copies']}  fast {len(r['fast'])}  roots {len(r['roots'])}")
    if r:
        np.save("player_fast.npy", np.array(r["fast"], dtype=np.uint64))
        json.dump(r["roots"], open("facing_root.json", "w"))

