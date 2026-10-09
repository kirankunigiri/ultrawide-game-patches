# Read-only access to the running RiftApart.exe: region enumeration and bulk reads.
import ctypes, ctypes.wintypes as wt, pymem

PROCESS = "RiftApart.exe"
MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
READABLE = {0x02, 0x04, 0x20, 0x40}          # R, RW, XR, XRW
WRITABLE = {0x04, 0x40}

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("__a", wt.DWORD), ("RegionSize", ctypes.c_ulonglong),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__b", wt.DWORD)]

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

pm = pymem.Pymem(PROCESS)
H = pm.process_handle
EXE = next(m for m in pm.list_modules() if m.name.lower() == PROCESS.lower())

def regions(writable_only=True, private_only=True, max_size=1 << 31):
    addr, mbi = 0, MBI()
    while k32.VirtualQueryEx(H, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        ok = (mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in (WRITABLE if writable_only else READABLE)
              and not (mbi.Protect & 0x700)        # no guard / no-cache / write-combine (GPU) pages
              and (not private_only or mbi.Type == MEM_PRIVATE)
              and mbi.RegionSize <= max_size)
        if ok:
            yield mbi.BaseAddress, mbi.RegionSize
        addr = mbi.BaseAddress + mbi.RegionSize

def read(addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(H, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]

def u64(a):
    b = read(a, 8); return int.from_bytes(b, "little") if b else None
