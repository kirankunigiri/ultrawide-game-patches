# Record (player world position, map icon array) while the pause map is open.
import json, sys, numpy as np
from pos import reread
from arr import icons

MAP_BASE = 0x1ace96e7168

def player_pos():
    a = np.load("player_cands.npy")
    v = reread(a)
    v = v[np.isfinite(v).all(1)]
    # the player = the largest cluster of near-identical copies
    best, bestn = None, 0
    for p in v[:: max(1, len(v) // 200)]:
        n = (np.abs(v - p).max(1) < 0.5).sum()
        if n > bestn:
            best, bestn = p, n
    near = v[np.abs(v - best).max(1) < 0.5]
    return np.median(near, 0).tolist(), int(bestn), len(v)

if __name__ == "__main__":
    p, n, tot = player_pos()
    ic = icons(MAP_BASE)
    print(f"player world {p[0]:.2f} {p[1]:.2f} {p[2]:.2f}  ({n}/{tot} copies agree)")
    for d in ic:
        print(f"  {d['img']:<22} vis={d['vis']} done={d['done']} map=({d['x']:.2f}, {d['y']:.2f}) rot={d['rot']}")
    if len(sys.argv) > 1:
        try:
            pairs = json.load(open("pairs.json"))
        except Exception:
            pairs = []
        pairs.append(dict(label=sys.argv[1], player=p, icons=ic))
        json.dump(pairs, open("pairs.json", "w"), indent=1)
        print("saved pair", sys.argv[1])
