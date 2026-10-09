# Find a map texture's name in memory and print float/int interpretations of nearby data,
# looking for MapMin / MapMax world bounds.
import re, struct, sys
from mem import regions, read

needle = (sys.argv[1] if len(sys.argv) > 1 else "sargasso_map_UV").encode()
pat = re.compile(re.escape(needle), re.I)
hits = 0
for base, size in regions(writable_only=False, private_only=False, max_size=1 << 30):
    b = read(base, size)
    if not b:
        continue
    for m in pat.finditer(b):
        hits += 1
        if hits > 12:
            break
        s = m.start()
        lo, hi = max(0, s - 256), min(len(b), s + 384)
        print(f"===== {base + s:#x}")
        txt = re.sub(rb"[^ -~]", b".", b[lo:hi]).decode()
        print("text:", txt)
        fl = []
        for o in range(lo - lo % 4, hi - 4, 4):
            v = struct.unpack_from("<f", b, o)[0]
            if 1.0 <= abs(v) <= 20000.0 and v == v and abs(v - round(v, 2)) < 1e-3:
                fl.append(f"{o - s:+d}:{v:g}")
        print("floats:", " ".join(fl))
print("hits:", hits)
