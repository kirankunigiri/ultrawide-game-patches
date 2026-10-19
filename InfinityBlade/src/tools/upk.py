# Minimal reader for the uncooked-compression UE3 packages in Infinity Blade II/III's iOS builds
# (CookedIPhone/*.xxx, package versions 864 and 868): name table, imports, exports.
import struct


class Pkg:
    def __init__(self, path):
        self.d = d = open(path, "rb").read()
        self.ver = struct.unpack_from("<H", d, 4)[0]
        p = 12
        folder = struct.unpack_from("<i", d, p)[0]
        p += 4 + (folder if folder >= 0 else -folder * 2)
        self.flags, ncount, noff, ecount, eoff, icount, ioff = struct.unpack_from("<Iiiiiii", d, p)
        self.names = []
        q = noff
        for _ in range(ncount):
            n = struct.unpack_from("<i", d, q)[0]
            q += 4
            self.names.append(d[q:q + n - 1].decode("latin1") if n > 0 else d[q:q - n * 2].decode("utf-16le"))
            q += (n if n > 0 else -n * 2) + 8  # + object flags
        self.imports = []
        q = ioff
        for _ in range(icount):
            _cpkg, _, cname, _, outer, oname, _ = struct.unpack_from("<iiiiiii", d, q)
            q += 28
            self.imports.append((self.names[cname], outer, self.names[oname]))
        self.exports = []
        q = eoff
        for _ in range(ecount):
            cls, _sup, outer, oname, _onum, _arch = struct.unpack_from("<iiiiii", d, q)
            q += 24 + 8  # + object flags
            size, off = struct.unpack_from("<ii", d, q)
            q += 8 + 4  # + export flags (no component map in these versions)
            ngen = struct.unpack_from("<i", d, q)[0]
            q += 4 + ngen * 4 + 16 + 4  # generations, package guid, package flags
            self.exports.append(dict(cls=cls, outer=outer, name=self.names[oname], size=size, off=off))

    def objname(self, ref):
        if ref > 0:
            return self.exports[ref - 1]["name"]
        if ref < 0:
            return self.imports[-ref - 1][2]
        return "None"

    def path(self, ref):
        parts = []
        while ref:
            parts.append(self.objname(ref))
            ref = self.exports[ref - 1]["outer"] if ref > 0 else self.imports[-ref - 1][1]
        return ".".join(reversed(parts))

    def owner_of(self, offset):
        """Index of the smallest export whose serialized data contains `offset`, or None."""
        best = None
        for i, e in enumerate(self.exports):
            if e["off"] <= offset < e["off"] + e["size"] and (best is None or e["size"] < self.exports[best]["size"]):
                best = i
        return best
