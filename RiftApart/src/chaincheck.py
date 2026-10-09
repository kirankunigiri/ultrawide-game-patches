# Validate pointer chains while driving the hero: keep chains that always resolve to the
# hero position (truth = median of the verified hero copies).
import json, struct, time, numpy as np
import drive
from mem import read, EXE
from pos import reread

lo = EXE.lpBaseOfDll
hero = np.load("hero_copies.npy")

def q(a):
    b = read(a, 8)
    return struct.unpack("<Q", b)[0] if b else None

def resolve(ch):
    """chain = (static_rva, [offsets...]) ; pointer hops then the last offset reaches the position."""
    rva, offs = ch
    p = q(lo + rva)
    for o in offs[:-1]:
        if not p:
            return None
        p = q(p + o)
    if not p:
        return None
    b = read(p + offs[-1], 12)
    return np.array(struct.unpack("<3f", b)) if b else None

if __name__ == "__main__":
    chains = []
    for c in json.load(open("chains1.json")):
        chains.append((int(c["static"][4:], 16), [c["off"]]))
    for c in json.load(open("chains2.json")):
        chains.append((int(c["static"][4:], 16), [c["off2"], c["off1"]]))
    print(len(chains), "chains to test")

    def truth():
        v = reread(hero)
        return np.median(v[np.isfinite(v).all(1)], 0)

    alive = list(chains)
    for k in ["", "w", "a", "s", "d", "w"]:
        if k:
            drive.focus(); drive.hold(k, 1.0); time.sleep(0.6)
        t = truth()
        keep = []
        for ch in alive:
            r = resolve(ch)
            if r is not None and np.isfinite(r).all() and np.abs(r - t).max() < 0.5:
                keep.append(ch)
        alive = keep
        print(f"after '{k or 'start'}': hero ({t[0]:.1f}, {t[2]:.1f})  chains still correct: {len(alive)}")
    json.dump([dict(static=f"exe+{r:#x}", offsets=o) for r, o in alive], open("chains_ok.json", "w"), indent=1)
    for r, o in alive[:20]:
        print(f"  exe+{r:#x} -> " + " -> ".join(f"+{x:#x}" for x in o))
