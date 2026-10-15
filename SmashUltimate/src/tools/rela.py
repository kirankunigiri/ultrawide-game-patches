import os
import struct,pickle
d=open(os.environ.get("NSO","main.nso"),'rb').read()
B=0x100
def u32(a): return struct.unpack_from("<I",d,a+B)[0]
def u64(a): return struct.unpack_from("<Q",d,a+B)[0]
mod0=u32(4); assert d[mod0+B:mod0+B+4]==b"MOD0", d[mod0+B:mod0+B+4]
dyn=mod0+struct.unpack_from("<i",d,mod0+B+4)[0]
tags={}
a=dyn
while True:
    t,v=u64(a),u64(a+8)
    if t==0: break
    tags.setdefault(t,v); a+=16
rela,relasz=tags[7],tags[8]
print("dyn",hex(dyn),"rela",hex(rela),"size",hex(relasz))
add2off={}
for i in range(relasz//24):
    off,info,addend=struct.unpack_from("<QQq",d,rela+B+i*24)
    if info&0xffffffff==1027: add2off.setdefault(addend,[]).append(off)
pickle.dump(add2off,open(os.environ.get("RELA_OUT","rela.pkl"),"wb"))
print("relative relocs",sum(len(v) for v in add2off.values()))
