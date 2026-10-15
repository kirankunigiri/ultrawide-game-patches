import os
import struct,sys,capstone
d=open(os.environ.get("NSO","main.nso"),'rb').read()
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
targets=[int(x,16) for x in sys.argv[1:]]
pages={t&~0xFFF:t for t in targets}
TEXT=0x39c7a90
words=struct.unpack_from("<%dI"%(TEXT//4),d,0x100)
res=[]
for i,w in enumerate(words):
    if (w&0x9F000000)!=0x90000000: continue
    pc=i*4
    imm=((w>>29)&3)|(((w>>5)&0x7FFFF)<<2)
    if imm&(1<<20): imm-=1<<21
    page=(pc&~0xFFF)+(imm<<12)
    if page not in pages: continue
    rd=w&31; t=pages[page]
    for j in range(1,10):
        if i+j>=len(words): break
        ins=next(md.disasm(struct.pack("<I",words[i+j]),pc+j*4),None)
        if ins and f"x{rd}, #{hex(t&0xFFF)}]" in ins.op_str or (ins and ins.mnemonic=="add" and ins.op_str.endswith(f"x{rd}, #{hex(t&0xFFF)}")):
            res.append((pc+j*4,ins.mnemonic,ins.op_str)); break
for r in res: print(hex(r[0]),r[1],r[2])
print(len(res),"refs")
