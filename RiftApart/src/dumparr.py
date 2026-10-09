import sys, struct
from mem import read

base = int(sys.argv[1], 16)
lo, hi = int(sys.argv[2]), int(sys.argv[3])
for i in range(lo, hi):
    a = base + i * 0xE8
    r = read(a, 0xE8)
    st = struct.unpack_from("<i", r, 0)[0]
    img = r[4:0x84].split(b"\0")[0].decode("latin-1").split("/")[-1]
    print(f"--- [{i}] {a:#x} st={st} img={img!r} vis={r[0x84]} done={r[0x85]}")
    tail = r[0x84:0xE8]
    for k in range(0, len(tail), 32):
        print(f"    +{0x84 + k:#05x}: {tail[k:k + 32].hex(' ')}")
    print("    as text @0x86:", tail[2:0x42].split(b"\0")[0][:64])
