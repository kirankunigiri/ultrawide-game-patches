import math
import struct
import unittest

from player_tracking import (HeroReader, HERO_HANDLE_RVA, ENTITY_POOL_RVA,
                             ENTITY_COUNT_RVA, ENTITY_STRIDE, SIGNATURES)


class Memory:
    def __init__(self):
        self.data = {}
        self.base = 0x140000000
        self.pool = 0x200000000
        self.transform = 0x300000000
        self.index, self.generation = 7, 2
        for rva, code in SIGNATURES.items():
            self.put(self.base + rva, code)
        self.pack(self.base + ENTITY_POOL_RVA, '<Q', self.pool)
        self.pack(self.base + ENTITY_COUNT_RVA, '<I', 32)
        self.bind()
        self.pose((120.4025, 8.05, -306.7213))

    def put(self, addr, data):
        self.data.update((addr+i, b) for i, b in enumerate(data))

    def pack(self, addr, fmt, *values):
        self.put(addr, struct.pack(fmt, *values))

    def read(self, addr, size):
        try:
            return bytes(self.data[addr+i] for i in range(size))
        except KeyError:
            return None

    @property
    def entity(self):
        return self.pool + self.index * ENTITY_STRIDE

    def bind(self):
        self.pack(self.base + HERO_HANDLE_RVA, '<I', self.generation << 20 | self.index)
        self.pack(self.entity, '<QH', self.transform, self.generation)

    def pose(self, xyz, angle=90):
        a = math.radians(angle)
        self.pack(self.transform, '<16f',
                  math.sin(a), 0, -math.cos(a), 0,
                  0, 1, 0, 0, math.cos(a), 0, math.sin(a), 0, *xyz, 1)


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.mem = Memory()
        self.reader = HeroReader(self.mem.read, self.mem.base)

    def test_live_pose_and_heading_share_transform(self):
        s = self.reader.sample()
        self.assertAlmostEqual(s.xz[0], 120.4025, places=3)
        self.assertAlmostEqual(s.xz[1], -306.7213, places=3)
        self.assertAlmostEqual(s.heading, 90)

    def test_old_zero_votes_cannot_override_native_entity(self):
        # The original bug: numerous aliases to the same zero-filled scratch memory.
        for i in range(64):
            self.mem.pack(self.mem.base+0x64FEFC0+i*8, '<Q', 0x400000000)
        self.mem.put(0x400000000, bytes(1024))
        self.assertAlmostEqual(self.reader.sample().xz[0], 120.4025, places=3)

    def test_new_entity_and_transform_followed_immediately(self):
        previous = self.reader.sample()
        self.mem.index = 8
        self.mem.transform += 0x1000
        self.mem.bind()
        self.mem.pose((600, 12, -50), angle=0)
        s = self.reader.sample()
        self.assertNotEqual(previous.entity, s.entity)
        self.assertEqual(s.xz, (600, -50))
        self.assertEqual(s.heading, 0)

    def test_pool_relocation(self):
        self.mem.pool += 0x10000
        self.mem.pack(self.mem.base + ENTITY_POOL_RVA, '<Q', self.mem.pool)
        self.mem.bind()
        self.assertEqual(self.reader.sample().entity, self.mem.entity)

    def test_stale_generation_rejected(self):
        self.assertIsNotNone(self.reader.sample())
        self.mem.pack(self.mem.entity+8, '<H', self.mem.generation+1)
        self.assertIsNone(self.reader.sample())

    def test_missing_transform_does_not_return_last_position(self):
        self.assertIsNotNone(self.reader.sample())
        self.mem.pack(self.mem.entity, '<Q', 0)
        self.assertIsNone(self.reader.sample())

    def test_null_handle_generation(self):
        self.mem.pack(self.mem.base+HERO_HANDLE_RVA, '<I', 7)
        self.assertIsNone(self.reader.sample())

    def test_out_of_range_index(self):
        self.mem.pack(self.mem.base+ENTITY_COUNT_RVA, '<I', 7)
        self.assertIsNone(self.reader.sample())

    def test_nan_zero_and_broken_matrices(self):
        for raw in (bytes(64), struct.pack('<16f', *([float('nan')]*16)),
                    struct.pack('<16f', *([1.0]*16))):
            with self.subTest(raw=raw):
                self.mem.put(self.mem.transform, raw)
                self.assertIsNone(self.reader.sample())

    def test_real_origin_is_valid_in_real_transform(self):
        self.mem.pose((0, 0, 0))
        self.assertEqual(self.reader.sample().xz, (0, 0))

    def test_real_teleport_is_not_filtered_or_averaged(self):
        self.reader.sample()
        self.mem.pose((800, 25, 300))
        self.assertEqual(self.reader.sample().xz, (800, 300))

    def test_short_read(self):
        original = self.mem.read
        self.reader.read = lambda a, n: b'\0' if a == self.mem.transform else original(a, n)
        self.assertIsNone(self.reader.sample())

    def test_game_code_mismatch(self):
        self.mem.put(self.mem.base+0xF1A520, b'\0')
        self.assertIsNone(self.reader.sample())
        self.assertIn('unsupported', self.reader.status)

    def test_slot_recycled_during_read(self):
        original = self.mem.read
        def race(addr, size):
            b = original(addr, size)
            if addr == self.mem.transform:
                self.mem.pack(self.mem.entity+8, '<H', self.mem.generation+1)
            return b
        self.reader.read = race
        self.assertIsNone(self.reader.sample())

    def test_handle_switched_during_read_retries_new_entity(self):
        original = self.mem.read
        old_transform = self.mem.transform
        def race(addr, size):
            b = original(addr, size)
            if addr == old_transform:
                self.mem.index += 1
                self.mem.transform += 0x1000
                self.mem.bind()
                self.mem.pose((300, 8, -100))
            return b
        self.reader.read = race
        self.assertEqual(self.reader.sample().xz, (300, -100))


if __name__ == '__main__':
    unittest.main()
