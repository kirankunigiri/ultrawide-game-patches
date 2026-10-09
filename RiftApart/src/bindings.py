# Decode Coherent UI data-binding registrations: for a bound type name, find its
# registration function and list (field name, struct offset, field type name).
import sys, re
from xrefs import data, base, off2rva, rva2off, refs_to, md

def cstr(rva, n=80):
    try:
        off = rva2off(rva)
    except Exception:
        return None
    s = data[off:off + n].split(b"\0")[0]
    return s.decode("latin-1") if s and all(32 <= c < 127 for c in s) else None

def decode(type_name):
    m = re.search(b"\x00" + re.escape(type_name.encode()) + b"\x00", data)
    if not m:
        print("no string", type_name); return
    srva = off2rva(m.start() + 1)
    for ref in refs_to(srva):
        start = ref
        off = rva2off(start)
        code = data[off: off + 0x1800]
        regs = {}          # register -> string/ptr rva loaded by lea
        stack = {}         # rsp offset -> value
        fields = []
        for ins in md.disasm(code, base + start):
            mn, ops = ins.mnemonic, ins.op_str
            if mn == "ret" or mn == "int3":
                break
            mm = re.match(r"lea (\w+), \[rip ([+-]) 0x([0-9a-f]+)\]", f"{mn} {ops}")
            if mm:
                tgt = ins.address + ins.size + (int(mm.group(3), 16) * (1 if mm.group(2) == "+" else -1)) - base
                regs[mm.group(1)] = tgt
                continue
            mm = re.match(r"mov qword ptr (\[r[sb]p [+-] (?:0x[0-9a-f]+|\d+)\]), (\w+)", f"{mn} {ops}")
            if mm and mm.group(2) in regs:
                stack[mm.group(1)] = regs[mm.group(2)]
                continue
            mm = re.match(r"mov dword ptr (\[r[sb]p [+-] (?:0x[0-9a-f]+|\d+)\]), (0x[0-9a-f]+|\d+)", f"{mn} {ops}")
            if mm:
                stack[mm.group(1)] = ("imm", int(mm.group(2), 0))
                continue
            if mn == "call" and "+ 0x18]" in ops:   # property-registration virtual call
                name = tname = offv = None
                for v in stack.values():
                    if isinstance(v, tuple):
                        offv = v[1]
                    elif isinstance(v, int):
                        s = cstr(v)
                        if s and name is None and v != stack.get("type"):
                            name = s
                        else:
                            tname = f"@{v:#x}"
                fields.append((name, offv, tname))
                stack = {}
        print(f"=== {type_name}  (registration at {base + ref:#x})")
        for n, o, t in fields:
            print(f"   +{o:#06x}  {n}   [{t}]" if o is not None else f"   ?       {n}   [{t}]")

if __name__ == "__main__":
    for t in sys.argv[1:]:
        decode(t)
