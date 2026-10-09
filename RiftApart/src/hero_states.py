"""Detect native hero states during which the overlay should hide (cutscenes, ...).

Each hero state class registers a component under its type descriptor; the class's
vtable slot +0x48 is a `lea rax, [descriptor]; ret` getter. RiftApart.exe 3.630.1.0
RVAs, resolved with rtti.vtables_for + that getter (see DEVELOPMENT.md). Read-only.
"""
import struct

DESCRIPTOR_SLOT = 0x48

# label: (descriptor RVA, Local-class vtable RVA)
HIDE_STATES = {
    "cutscene": (0x6015870, 0x2F645C0),         # HeroStateCinematicLocal
    "cutscene move": (0x601F0E0, 0x2F7B4A0),    # HeroStateCinematicMoveLocal
}


def find_component(read_bytes, entity, key):
    """The game's component lookup: entity +0x80 table, +0x88 capacity, linear probing.
    Returns (component, table header, slot address, slot bytes) or None."""
    raw = read_bytes(entity + 0x80, 10)
    if raw is None:
        return None
    table, capacity = struct.unpack("<QH", raw)
    if not table or not 1 <= capacity <= 4096 or capacity & (capacity - 1):
        return None
    slot = (key >> 4) & (capacity - 1)
    for _ in range(capacity):
        entry = read_bytes(table + slot * 16, 16)
        if entry is None:
            return None
        found, ptr = struct.unpack("<QQ", entry)
        if not found:
            return None
        if found == key:
            return ptr, raw, table + slot * 16, entry
        slot = (slot + 1) & (capacity - 1)
    return None


class HeroStateReader:
    def __init__(self, hero_reader, image_base, states=HIDE_STATES):
        self.hero = hero_reader
        self.base = image_base
        self.states = states
        self.profile_ok = None

    def _validate(self):
        """Every vtable's descriptor getter must return its descriptor on this build."""
        for descriptor, vtable in self.states.values():
            getter = self.hero._bytes(self.base + vtable + DESCRIPTOR_SLOT, 8)
            code = self.hero._bytes(struct.unpack("<Q", getter)[0], 8) if getter else None
            if (code is None or code[:3] != b"\x48\x8d\x05" or code[7] != 0xC3
                    or struct.unpack("<Q", getter)[0] + 7 + struct.unpack_from("<i", code, 3)[0]
                    != self.base + descriptor):
                return False
        return True

    def active(self, entity):
        """Label of the first active hide-state on this hero entity, else None.
        Unknown/unsupported reads return None (never hide on doubt)."""
        if self.profile_ok is None:
            self.profile_ok = self._validate()
        if not self.profile_ok:
            return None
        for label, (descriptor, vtable) in self.states.items():
            hit = find_component(self.hero._bytes, entity, self.base + descriptor)
            if hit is None:
                continue
            head = self.hero._bytes(hit[0], 0x18)
            if (head is not None and struct.unpack_from("<Q", head)[0] == self.base + vtable
                    and struct.unpack_from("<Q", head, 0x10)[0] == entity):
                return label
        return None
