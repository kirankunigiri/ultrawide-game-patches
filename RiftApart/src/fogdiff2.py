# Filtered diff: pages that ALREADY held data (old exploration) and gained a few bits only.
import json, sys, numpy as np
from mem import read

NAME = sys.argv[1] if len(sys.argv) > 1 else "fog_snap"
OUT = sys.argv[2] if len(sys.argv) > 2 else "fog_candidates.json"
idx = json.load(open(NAME + ".json"))
out = []
with open(NAME + ".bin", "rb") as f:
    for base, size, off in idx:
        new = read(base, size)
        if not new or len(new) != size or size % 4096:
            continue
        f.seek(off)
        old = np.frombuffer(f.read(size), np.uint8).reshape(-1, 4096)
        nw = np.frombuffer(new, np.uint8).reshape(-1, 4096)
        ch = (old != nw)
        for pg in np.nonzero(ch.any(1))[0]:
            o, n, c = old[pg], nw[pg], ch[pg]
            k = int(c.sum())
            if not (1 <= k <= 600):
                continue
            if ((o & ~n) != 0).any():            # something switched off -> not a visited mask
                continue
            if np.count_nonzero(o) < 16:          # page was (nearly) empty before -> fresh data
                continue
            vals = sorted(set(int(x) for x in n[c]))[:8]
            out.append(dict(addr=base + int(pg) * 4096, changed=k, nz_before=int(np.count_nonzero(o)),
                            nz_after=int(np.count_nonzero(n)), first=int(np.nonzero(c)[0][0]),
                            last=int(np.nonzero(c)[0][-1]), new_values=vals))
out.sort(key=lambda d: -d["changed"])
print(len(out), "candidate pages")
for d in out[:40]:
    print(f"  {d['addr']:#x}: +{d['changed']:3d} bytes  nonzero {d['nz_before']}->{d['nz_after']}  "
          f"span {d['first']}..{d['last']}  new values {d['new_values']}")
json.dump(out, open(OUT, "w"), indent=1)

