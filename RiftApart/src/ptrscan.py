# Pointer scan: find chains  [exe static] -> obj1 (+off1) -> ... -> hero position copy.
#   level 1: static qword q with  target - q in [0, MAXOFF)
#   level 2: heap qword at H pointing into a target object; static pointing near H
import numpy as np, json, sys
from mem import regions, read, EXE

MAXOFF = 0x1000
TARGETS = sys.argv[2] if len(sys.argv) > 2 else "hero_copies.npy"
PREFIX = sys.argv[3] if len(sys.argv) > 3 else "chains"
targets = np.sort(np.load(TARGETS).astype(np.uint64))
lo, hi = EXE.lpBaseOfDll, EXE.lpBaseOfDll + EXE.SizeOfImage

def scan(regs, tgts, maxoff):
    """Yield (location, value, target, offset) for qwords pointing into [t - maxoff, t]."""
    tg = np.sort(tgts)
    for base, size in regs:
        b = read(base, size)
        if not b:
            continue
        q = np.frombuffer(b[: len(b) // 8 * 8], np.uint64)
        # candidate pointer values must fall inside [min target - maxoff, max target]
        m = (q >= tg[0] - np.uint64(maxoff)) & (q <= tg[-1])
        for i in np.nonzero(m)[0]:
            val = q[i]
            j = np.searchsorted(tg, val)                  # first target >= val
            if j < len(tg) and tg[j] - val < maxoff:
                yield base + int(i) * 8, int(val), int(tg[j]), int(tg[j] - val)

exe_regs = [(b, s) for b, s in regions(writable_only=True, private_only=False) if lo <= b < hi]
print(f"exe writable regions: {len(exe_regs)}, {sum(s for _, s in exe_regs) / 1e6:.1f} MB")
lvl1 = list(scan(exe_regs, targets, MAXOFF))
print(f"level 1 (static -> hero copy): {len(lvl1)}")
for loc, val, t, off in lvl1[:20]:
    print(f"  [exe+{loc - lo:#x}] = {val:#x}  +{off:#x} -> {t:#x}")

if len(sys.argv) > 1 and sys.argv[1] == "2":
    # level 2: heap holders pointing into hero objects, then statics pointing near holders
    heap = list(regions())
    holders = {}
    for loc, val, t, off in scan(heap, targets, 0x400):
        holders[loc] = (val, t, off)
    print(f"heap holders: {len(holders)}")
    hl = np.array(sorted(holders), dtype=np.uint64)
    res = []
    for sloc, sval, h, off2 in scan(exe_regs, hl, 0x400):
        val, t, off1 = holders[h]
        res.append(dict(static=f"exe+{sloc - lo:#x}", off2=off2, off1=off1, target=hex(t)))
    print(f"level 2 chains: {len(res)}")
    for r in res[:30]:
        print(f"  [{r['static']}] +{r['off2']:#x} -> [ptr] +{r['off1']:#x} = hero copy {r['target']}")
    json.dump(res, open(PREFIX + "2.json", "w"), indent=1)
json.dump([dict(static=f"exe+{loc - lo:#x}", off=off, target=hex(t)) for loc, val, t, off in lvl1],
          open(PREFIX + "1.json", "w"), indent=1)

