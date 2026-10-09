# Name every component on the hero (RTTI) to see which run state exists. Read-only.
import struct, mem
from player_tracking import HeroReader
b = mem.EXE.lpBaseOfDll
def names():
    h = HeroReader(mem.read, b).sample()
    if not h: return None
    t, n = struct.unpack('<QH', mem.read(h.entity + 0x80, 10))
    out = {}
    for i in range(n):
        k, p = struct.unpack('<QQ', mem.read(t + 16 * i, 16))
        if not k or not p: continue
        try:
            v = mem.u64(p); col = mem.u64(v - 8); raw = mem.read(col, 24)
            nm = mem.read(b + struct.unpack_from('<I', raw, 12)[0] + 16, 80).split(b'\0')[0].decode()
        except Exception:
            nm = '?'
        out[hex(k - b)] = (nm, hex(p))
    return out
if __name__ == '__main__':
    for k, v in sorted(names().items(), key=lambda kv: kv[1][0]):
        print(k, v)
