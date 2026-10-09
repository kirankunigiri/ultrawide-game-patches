# List distinct texture/asset path strings in game memory that look map-related.
import re, collections
from mem import regions, read

pat = re.compile(rb"[A-Za-z0-9_/\\.\-]{6,160}\.(texture|material|config|level|model)\x00")
want = re.compile(rb"(?i)(map|fow|fogofwar|reveal)")
found = collections.Counter()
for base, size in regions(writable_only=False, private_only=False, max_size=1 << 30):
    b = read(base, size)
    if not b:
        continue
    for m in pat.finditer(b):
        s = m.group()[:-1]
        if want.search(s):
            found[s.decode("latin-1")] += 1
for s, n in sorted(found.items()):
    print(f"{n:5d}  {s}")
