# Static analysis of RiftApart.exe on disk: find code that references given strings
# (RIP-relative LEA), and disassemble around each reference.
import sys, re, numpy as np, pefile, capstone

EXE = r"C:\Games\Solo\Ratchet & Clank Rift Apart\RiftApart.exe"
pe = pefile.PE(EXE, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = open(EXE, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
t_raw, t_rva = text.PointerToRawData, text.VirtualAddress
tb = np.frombuffer(data, np.uint8, text.SizeOfRawData, t_raw)

def off2rva(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return off - s.PointerToRawData + s.VirtualAddress
def rva2off(rva):
    return pe.get_offset_from_rva(rva)

# every 4-byte little-endian disp at text offset i, as if rip-relative ending at i+4
disp = (tb[:-3].astype(np.int64) | tb[1:-2].astype(np.int64) << 8 |
        tb[2:-1].astype(np.int64) << 16 | tb[3:].astype(np.int64) << 24)
disp = np.where(disp >= 2**31, disp - 2**32, disp)
pos_rva = t_rva + np.arange(len(disp))  # rva of the disp field

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

def refs_to(target_rva, max_show=6, before=0x60, after=0x80):
    # instruction end = disp field + 4 (+ imm for some forms; LEA/MOV have none)
    hits = np.nonzero(pos_rva + 4 + disp == target_rva)[0]
    out = []
    for h in hits:
        # expect opcode 8D (lea) or 8B (mov) 1 byte before modrm before disp
        modrm, op = tb[h - 1], tb[h - 2]
        if modrm & 0xC7 != 0x05 or op not in (0x8D, 0x8B): continue
        out.append(t_rva + h - 3)  # approx instruction start (REX + op + modrm)
    return out

def dis(rva, before=0x40, after=0x80):
    off = rva2off(rva - before)
    code = data[off: off + before + after]
    lines = []
    for ins in md.disasm(code, base + rva - before):
        mark = ">>" if ins.address == base + rva else "  "
        lines.append(f"{mark} {ins.address:x}: {ins.mnemonic} {ins.op_str}")
    return "\n".join(lines)

if __name__ == "__main__":
    for name in sys.argv[1:]:
        for m in re.finditer(re.escape(name.encode()) + b"\x00", data):
            srva = off2rva(m.start())
            r = refs_to(srva)
            print(f"=== '{name}' at rva {srva:#x}: {len(r)} code refs")
            for x in r[:4]:
                print(dis(x)); print("-" * 60)
