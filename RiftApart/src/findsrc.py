# Search the game's memory for UI source text (HTML/JS/CSS) mentioning given words and
# print the surrounding context (ASCII and UTF-16).
import re, sys, collections
from mem import regions, read

words = [w.encode() for w in sys.argv[1:]] or [b"map_bg"]
pat = re.compile(b"|".join(re.escape(w) for w in words))
pat16 = re.compile(b"|".join(re.escape(w.decode().encode("utf-16-le")) for w in words))
seen = collections.OrderedDict()
for base, size in regions(writable_only=False, private_only=False, max_size=1 << 30):
    b = read(base, size)
    if not b:
        continue
    for m in pat.finditer(b):
        ctx = b[max(0, m.start() - 300): m.end() + 300]
        txt = re.sub(rb"[^ -~\n\t]", b".", ctx).decode()
        key = txt[250:400]
        if key not in seen:
            seen[key] = (base + m.start(), txt)
    for m in pat16.finditer(b):
        ctx = b[max(0, m.start() - 600): m.end() + 600]
        try:
            txt = ctx.decode("utf-16-le", "replace")
        except Exception:
            continue
        key = "u16" + txt[250:400]
        if key not in seen:
            seen[key] = (base + m.start(), "[utf16] " + re.sub(r"[^ -~\n\t]", ".", txt))
print(len(seen), "distinct contexts")
for k, (a, t) in list(seen.items())[:40]:
    print(f"===== {a:#x}\n{t}\n")
