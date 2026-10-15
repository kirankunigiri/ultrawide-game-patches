import os
import sys,capstone,struct
d=open(os.environ.get("NSO","main.nso"),'rb').read()
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
def rd(mem,n=4): return d[mem+0x100:mem+0x100+n]
def dis(mem,before=40,after=40,mark=()):
    start=mem-before*4
    for ins in md.disasm(rd(start,(before+after)*4), start):
        m=" <==" if ins.address in mark else ""
        print(f"{ins.address:08X}  {ins.bytes.hex()}  {ins.mnemonic:8} {ins.op_str}{m}")
if __name__=="__main__":
    mem=int(sys.argv[1],16); b=int(sys.argv[2]) if len(sys.argv)>2 else 40; a=int(sys.argv[3]) if len(sys.argv)>3 else 40
    dis(mem,b,a,{mem})
