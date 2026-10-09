import struct
import unittest
from hero_states import HeroStateReader, HIDE_STATES, DESCRIPTOR_SLOT
from player_tracking import HeroReader
from test_player_tracking import Memory


class HeroStateTests(unittest.TestCase):
    def setUp(self):
        self.m = Memory()
        self.table, self.capacity = 0x400000000, 8
        self.m.pack(self.m.entity + 0x80, "<QH", self.table, self.capacity)
        self.m.put(self.table, bytes(self.capacity * 16))
        # Descriptor getters: lea rax, [rip + disp]; ret
        for i, (descriptor, vtable) in enumerate(HIDE_STATES.values()):
            getter = self.m.base + 0x100000 + i * 0x10
            disp = (self.m.base + descriptor) - (getter + 7)
            self.m.put(getter, b"\x48\x8d\x05" + struct.pack("<i", disp) + b"\xc3")
            self.m.pack(self.m.base + vtable + DESCRIPTOR_SLOT, "<Q", getter)
        self.r = HeroStateReader(HeroReader(self.m.read, self.m.base), self.m.base)

    def add(self, label, vtable=None, owner=None):
        descriptor, vt = HIDE_STATES[label]
        key = self.m.base + descriptor
        slot = (key >> 4) & (self.capacity - 1)
        while self.m.read(self.table + slot * 16, 8) != bytes(8):
            slot = (slot + 1) & (self.capacity - 1)
        ptr = 0x500000000 + slot * 0x100
        self.m.pack(self.table + slot * 16, "<QQ", key, ptr)
        self.m.pack(ptr, "<QQQ", vtable or self.m.base + vt, 0, owner or self.m.entity)

    def test_gameplay_is_not_hidden(self):
        self.assertIsNone(self.r.active(self.m.entity))

    def test_cutscene_hides(self):
        self.add("cutscene")
        self.assertEqual(self.r.active(self.m.entity), "cutscene")

    def test_wrong_class_or_owner_is_ignored(self):
        self.add("cutscene", vtable=0x123)
        self.assertIsNone(self.r.active(self.m.entity))
        self.setUp()
        self.add("cutscene", owner=0x999)
        self.assertIsNone(self.r.active(self.m.entity))

    def test_changed_build_never_hides(self):
        self.add("cutscene")
        descriptor, vtable = HIDE_STATES["cutscene"]
        self.m.pack(self.m.base + vtable + DESCRIPTOR_SLOT, "<Q", 0)
        self.assertIsNone(self.r.active(self.m.entity))


if __name__ == "__main__":
    unittest.main()
