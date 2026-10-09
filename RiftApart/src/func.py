# Disassemble the function containing an address, and list call sites that call it.
import sys, numpy as np
from xrefs import data, base, rva2off, md, t_rva, tb, off2rva

addr = int(sys.argv[1], 16) - base
# function start: walk back to the int3 padding
off = rva2off(addr)
while not (data[off - 1] == 0xCC and data[off - 2] == 0xCC):
    off -= 1
start = off2rva(off)
print(f"function starts at {base + start:#x}")
for ins in md.disasm(data[off: off + 0x180], base + start):
    print(f"  {ins.address:x}: {ins.mnemonic} {ins.op_str}")
    if ins.mnemonic == "ret":
        break
# callers: E8 rel32 whose target == start
disp = (tb[1:-3].astype(np.int64) | tb[2:-2].astype(np.int64) << 8 | tb[3:-1].astype(np.int64) << 16 | tb[4:].astype(np.int64) << 24)
disp = np.where(disp >= 2**31, disp - 2**32, disp)
pos = t_rva + np.arange(len(disp))
calls = np.nonzero((tb[:-4] == 0xE8) & (pos + 5 + disp == start))[0]
print("callers:", [hex(base + t_rva + int(c)) for c in calls[:10]])
for c in calls[:3]:
    co = rva2off(t_rva + int(c))
    print(f"--- around caller {base + t_rva + int(c):#x}")
    for ins in md.disasm(data[co - 0x30: co + 8], base + t_rva + int(c) - 0x30):
        print(f"  {ins.address:x}: {ins.mnemonic} {ins.op_str}")
