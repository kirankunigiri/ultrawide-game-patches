# Summarize each LMB hold from glitch_log.jsonl: state before, time to steady firing.
import json, sys
rows = [json.loads(l) for l in open("glitch_log.jsonl") if l.strip().endswith("]")]
print("rows", len(rows), "span", rows[0][0], rows[-1][0])
i = 0
while i < len(rows):
    if rows[i][1] and (i == 0 or not rows[i-1][1]):
        j = i
        while j < len(rows) and rows[j][1]: j += 1
        pre = rows[max(0, i-15):i]
        seg = rows[i:j]
        fire = [r[0] for r in seg if "Firing" in r[6]]
        first = fire[0] - rows[i][0] if fire else None
        print(f"\nLMB {rows[i][0]:.3f} hold {rows[j-1][0]-rows[i][0]:.2f}s first-firing {first} pre-tog/mode {[ (r[7], r[8]) for r in pre[-4:]]} pre-state {pre[-1][5] if pre else ''}")
        if len(sys.argv) > 1:
            prev = None
            for r in rows[max(0, i-10):min(j+10, len(rows))]:
                k = r[1:]
                if k != prev: print("  ", r)
                prev = k
        i = j
    i += 1
