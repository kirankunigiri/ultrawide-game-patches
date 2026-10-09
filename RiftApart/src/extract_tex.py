# Extract .texture assets from Rift Apart's archives to PNG, using ALERT's dat1lib
# (https://github.com/Tkachov/ALERT, GPLv3). DDS assembly mirrors ALERT's server/state/textures.py.
import io, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "ALERT"))
import dat1lib, dat1lib.types.toc, dat1lib.types.autogen
import dat1lib.types.sections.texture.header as texhdr
from PIL import Image

GAME = r"C:\Games\Solo\Ratchet & Clank Rift Apart"
_toc = None

def toc():
    global _toc
    if _toc is None:
        with open(os.path.join(GAME, "toc"), "rb") as f:
            _toc = dat1lib.read(f)
        _toc.set_archives_dir(GAME)
    return _toc

def find(path):
    t = toc()
    for p in {path, path.replace("\\", "/"), path.replace("/", "\\"), path.lower(), path.lower().replace("\\", "/")}:
        e = t.get_asset_entries_by_path(p)
        if e:
            return e
    return []

def make_dds(asset, hd_data, mip):
    info = asset.dat1.get_section(texhdr.TextureHeaderSection.TAG)
    mips, hd_px, sd_px = [], 0, 0
    if hd_data is not None:
        w, h = info.hd_width, info.hd_height
        for _ in range(info.hd_mipmaps):
            hd_px += w * h; mips.append((w, h)); w //= 2; h //= 2
    w, h = info.sd_width, info.sd_height
    for _ in range(info.sd_mipmaps):
        sd_px += w * h; mips.append((w, h)); w //= 2; h //= 2
    hd_bpp = info.hd_len / hd_px if hd_px else 0
    sd_bpp = info.sd_len / sd_px if sd_px else 0
    w, h = mips[mip]
    dds = b"DDS \x7C\x00\x00\x00\x07\x10\x0A\x00" + struct.pack("<II", h, w)
    dds += struct.pack("<III", (w * 32 + 7) // 8, 0, 0) + b"\x00" * 44
    dds += b"\x20\x00\x00\x00\x04\x00\x00\x00DX10" + b"\x00" * 20 + b"\x00\x10\x00\x00" + b"\x00" * 16
    dds += struct.pack("<5I", info.fmt, 3 if h > 1 else 2, 0, 1, 0)
    if hd_data is not None and mip < info.hd_mipmaps:
        off = sum(int(hd_bpp * a * b) for a, b in mips[:mip])
        return dds + hd_data[off:], info
    hdn = info.hd_mipmaps if hd_data is not None else 0
    off = 0x80 - 36 + sum(int(sd_bpp * a * b) for a, b in mips[hdn: hdn + (mip - hdn)])
    return dds + asset._raw_dat1[off:], info

def extract(path, out_png):
    entries = find(path)
    if not entries:
        return f"not found: {path}"
    blobs = [(e, toc().extract_asset(e)) for e in entries]
    # the parsable .texture header asset vs the raw HD pixel blob
    asset, hd = None, None
    for e, data in blobs:
        try:
            a = dat1lib.read(io.BytesIO(data))
            if isinstance(a, dat1lib.types.autogen.Texture):
                asset = asset or a
                continue
        except Exception:
            pass
        hd = data if hd is None or len(data) > len(hd) else hd
    if asset is None:
        return f"no texture header in {len(blobs)} entries for {path}"
    if hd is not None and not any(hd[:: max(1, len(hd) // 4096)]):
        # GDeflate-compressed HD stream and no libdeflate.dll: dat1lib returns zeros.
        # Fall back to the uncompressed SD mips inside the header asset.
        hd = None
    dds, info = make_dds(asset, hd, 0)
    img = Image.open(io.BytesIO(dds))
    img.save(out_png)
    return f"{path}: fmt={info.fmt} {img.size} hd={'yes' if hd else 'no'} -> {os.path.basename(out_png)}"

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "maps"), exist_ok=True)
    for p in sys.argv[1:]:
        name = os.path.splitext(os.path.basename(p.replace("\\", "/")))[0]
        try:
            print(extract(p, os.path.join(HERE, "maps", name + ".png")))
        except Exception as ex:
            import traceback; traceback.print_exc()
            print("FAILED", p, ex)
