import struct, sys, capstone
DOL = sys.argv[1] if __name__ == "__main__" else None
class Dol:
    def __init__(s, path):
        d = open(path, 'rb').read(); s.d = d
        offs = struct.unpack('>18I', d[0:72]); addrs = struct.unpack('>18I', d[72:144]); sizes = struct.unpack('>18I', d[144:216])
        s.secs = [(i, offs[i], addrs[i], sizes[i]) for i in range(18) if sizes[i]]
        s.md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_PS)
    def off(s, a):
        for i, o, ad, sz in s.secs:
            if ad <= a < ad + sz: return o + a - ad
        return None
    def read(s, a, n):
        o = s.off(a); return s.d[o:o+n] if o is not None else None
    def u32(s, a): return struct.unpack('>I', s.read(a, 4))[0]
    def f32(s, a): return struct.unpack('>f', s.read(a, 4))[0]
    def dis(s, a, before=20, after=20, mark=()):
        st = a - before*4
        for ins in s.md.disasm(s.read(st, (before+after)*4), st):
            m = ' <==' if ins.address in mark or ins.address == a else ''
            print(f"{ins.address:08X}  {ins.bytes.hex()}  {ins.mnemonic:9} {ins.op_str}{m}")
    def text_words(s):
        for i, o, ad, sz in s.secs:
            if i < 7:
                for k in range(0, sz, 4): yield ad + k, struct.unpack('>I', s.d[o+k:o+k+4])[0]

def dis2(d, a, before=20, after=20, mark=()):
    st = a - before*4
    for k in range(before+after):
        ad = st + 4*k; b = d.read(ad, 4)
        if b is None: break
        ins = next(d.md.disasm(b, ad), None)
        m = ' <==' if ad in mark or ad == a else ''
        if ins: print(f"{ad:08X}  {b.hex()}  {ins.mnemonic:9} {ins.op_str}{m}")
        else: print(f"{ad:08X}  {b.hex()}  .word{m}")

def func_bounds(d, a):
    # walk back to 'stwu r1,-X(r1)' and forward to 'blr'
    s = a
    while True:
        w = d.u32(s)
        if (w & 0xFFFF0000) == 0x94210000: break
        s -= 4
    e = a
    while d.u32(e) != 0x4E800020: e += 4
    return s, e

def find_str(d, s):
    out=[]; b=s.encode()+b'\0'
    for i,o,ad,sz in d.secs:
        data=d.d[o:o+sz]; k=data.find(b)
        while k>=0:
            out.append(ad+k); k=data.find(b,k+1)
    return out

def xrefs(d, target):
    """lis rX,hi ; addi/ori rY,rX,lo  (within 8 instrs) -> target"""
    hi=(target+0x8000)>>16 & 0xFFFF; lo=target & 0xFFFF
    res=[]; words=list(d.text_words())
    for idx,(a,w) in enumerate(words):
        if (w>>26)==15 and (w&0xFFFF)==hi and ((w>>16)&31)==0:
            rx=(w>>21)&31
            for a2,w2 in words[idx+1:idx+12]:
                if (w2>>26) in (14,24) and ((w2>>16)&31)==rx and (w2&0xFFFF)==lo: res.append(a2); break
    return res
