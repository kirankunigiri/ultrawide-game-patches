# Find live instances of a C++ class via MSVC RTTI: type descriptor -> complete object
# locator -> vtable; then scan writable memory for objects whose first qword is the vtable.
import sys, struct, numpy as np, pefile
from mem import regions, read, EXE

EXE_PATH = r"C:\Games\Solo\Ratchet & Clank Rift Apart\RiftApart.exe"
pe = pefile.PE(EXE_PATH, fast_load=True)
data = open(EXE_PATH, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase

def off2rva(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return off - s.PointerToRawData + s.VirtualAddress

def vtables_for(cls):
    name = f".?AV{cls}@@".encode() + b"\0"
    i = data.find(name)
    if i < 0:
        return []
    td_rva = off2rva(i) - 0x10
    arr = np.frombuffer(data[: len(data) // 4 * 4], np.uint32)
    vts = []
    for idx in np.nonzero(arr == td_rva)[0]:
        col_off = idx * 4 - 12                     # pTypeDescriptor is at COL+12
        if col_off < 0 or struct.unpack_from("<I", data, col_off)[0] != 1:
            continue
        col_rva = off2rva(col_off)
        if struct.unpack_from("<I", data, col_off + 20)[0] != col_rva:   # pSelf
            continue
        q = np.frombuffer(data[: len(data) // 8 * 8], np.uint64)
        for j in np.nonzero(q == IMG + col_rva)[0]:
            vts.append(off2rva(j * 8) + 8)          # vtable starts right after the COL pointer
    return vts

def instances(vt_rva, limit=20):
    target = np.uint64(EXE.lpBaseOfDll + vt_rva)
    found = []
    for base, size in regions():
        b = read(base, size)
        if not b:
            continue
        q = np.frombuffer(b[: len(b) // 8 * 8], np.uint64)
        for k in np.nonzero(q == target)[0]:
            found.append(base + int(k) * 8)
            if len(found) >= limit:
                return found
    return found

if __name__ == "__main__":
    cls = sys.argv[1]
    vts = vtables_for(cls)
    print(cls, "vtables:", [hex(v) for v in vts])
    for v in vts:
        for inst in instances(v):
            print(f"  instance at {inst:#x}")
            b = read(inst, 0x100)
            for o in range(0, 0x100, 8):
                qv = struct.unpack_from("<Q", b, o)[0]
                f1, f2 = struct.unpack_from("<2f", b, o)
                i1, i2 = struct.unpack_from("<2i", b, o)
                print(f"    +{o:#05x}: {qv:#018x}  i=({i1}, {i2})  f=({f1:.4g}, {f2:.4g})")
