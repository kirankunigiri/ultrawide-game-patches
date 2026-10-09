# Dump an object and summarise what each pointer field points to (heap buffers).
import sys, struct
from mem import read, EXE

obj = int(sys.argv[1], 16); size = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x200
lo, hi = EXE.lpBaseOfDll, EXE.lpBaseOfDll + EXE.SizeOfImage
b = read(obj, size)
for o in range(0, size, 8):
    q = struct.unpack_from("<Q", b, o)[0]
    note = ""
    if lo <= q < hi:
        note = f"exe+{q - lo:#x}"
    elif 0x10000 < q < 0x7ff000000000:
        t = read(q, 64)
        if t:
            nz = sum(1 for x in t if x)
            note = f"heap -> {t[:32].hex(' ')}  ({nz}/64 nonzero)"
    if q:
        print(f"+{o:#05x}: {q:#018x}  {note}")
