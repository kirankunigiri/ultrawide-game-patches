# Find the explored-area (fog of war) data by diffing memory while revealing new ground.
#   python fogdiff.py snap   # at the edge of unexplored ground
#   python fogdiff.py diff   # after walking into unexplored ground
# Reports 4 KB pages whose changes are ONLY bits switching on (never off) - the signature
# of a "visited" bitmap or a reveal mask - ranked by how many bytes changed.
import sys, json, os, numpy as np
from mem import regions, read

NAME = sys.argv[2] if len(sys.argv) > 2 else "fog_snap"
SNAP, IDX = NAME + ".bin", NAME + ".json"

def snap():
    idx = []
    with open(SNAP, "wb") as f:
        for base, size in regions():
            b = read(base, size)
            if not b:
                continue
            idx.append((base, len(b), f.tell()))
            f.write(b)
    json.dump(idx, open(IDX, "w"))
    print(f"snapshot: {len(idx)} regions, {sum(x[1] for x in idx) / 1e9:.2f} GB")

def diff():
    idx = json.load(open(IDX))
    out = []
    with open(SNAP, "rb") as f:
        for base, size, off in idx:
            new = read(base, size)
            if not new or len(new) != size:
                continue
            f.seek(off)
            old = np.frombuffer(f.read(size), np.uint8)
            nw = np.frombuffer(new, np.uint8)
            ch = old != nw
            if not ch.any():
                continue
            pages = np.nonzero(ch.reshape(-1, 4096).any(1))[0] if size % 4096 == 0 else []
            for pg in pages:
                s = slice(pg * 4096, pg * 4096 + 4096)
                o, n = old[s], nw[s]
                c = o != n
                set_only = ((n & ~o) != 0) & ((o & ~n) == 0)
                cleared = ((o & ~n) != 0)
                if c.sum() and not cleared.any() and set_only[c].all():
                    out.append((int(c.sum()), base + pg * 4096, int(np.count_nonzero(n))))
    out.sort(reverse=True)
    print(f"{len(out)} pages changed with bits only switching on")
    for n, addr, nz in out[:40]:
        print(f"  {addr:#x}: {n:4d} bytes gained bits   ({nz} nonzero bytes in page)")
    json.dump(out[:400], open("fog_candidates.json", "w"))

if __name__ == "__main__":
    {"snap": snap, "diff": diff}[sys.argv[1]]()

