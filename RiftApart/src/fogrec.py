import struct, sys
from fogread import table
from mem import read

key = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0xbd52b112
rec = dict(table())[key]
b = read(rec, 0x90)
for o in range(0, 0x90, 4):
    f = struct.unpack_from("<f", b, o)[0]; i = struct.unpack_from("<i", b, o)[0]
    print(f"+{o:#04x}: {b[o:o+4].hex()}  f={f:14.4f}  i={i}")
