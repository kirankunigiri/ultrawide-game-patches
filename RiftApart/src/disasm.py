# Disassemble address ranges / whole functions from RiftApart.exe (until ret).
import sys
from xrefs import data, base, rva2off, md

for arg in sys.argv[1:]:
    a, _, n = arg.partition(":")
    a = int(a, 16); n = int(n, 16) if n else 0x400
    print(f"===== {a:#x}")
    for ins in md.disasm(data[rva2off(a - base): rva2off(a - base) + n], a):
        print(f"  {ins.address:x}: {ins.mnemonic} {ins.op_str}")
        if not n or (ins.mnemonic in ("ret", "int3") and arg.find(":") < 0):
            if ins.mnemonic in ("ret", "int3"):
                break
