"""Read the native pause map's hero transform without injecting/calling game code.

Profile: RiftApart.exe 3.630.1.0. See TRACKING.md for disassembly evidence.
This module deliberately has no process/Windows imports so failure paths can be tested.
"""
from dataclasses import dataclass
import math
import struct


HERO_HANDLE_RVA = 0x6003E88
ENTITY_POOL_RVA = 0x6748978
ENTITY_COUNT_RVA = 0x6748994
ENTITY_STRIDE = 0xC0

# Validate the actual instructions used to derive the layout, including the map caller.
# RIP-relative instructions have the same bytes under ASLR.
SIGNATURES = {
    0x5EC8E9: bytes.fromhex('488d0d9875a105'),
    0x5EC90A: bytes.fromhex('e811dc9200'),
    0x5EC917: bytes.fromhex('e8a42ecbff'),
    0xF1A520: bytes.fromhex(
        '448b01418bd0c1ea1481e2ff070000742d4181e0ffff0f004b8d0c40'
        '48c1e10648030d31e48205443b0546e4820573080fb741083bd07402'
        '33c9488bc1c333c0c3'),
    0x29F7C0: bytes.fromhex('4883ec28488b014885c074094883c0304883c428c3'),
}


@dataclass(frozen=True)
class HeroSample:
    handle: int
    entity: int
    transform: int
    xyz: tuple
    heading: float

    @property
    def xz(self):
        return self.xyz[0], self.xyz[2]


class HeroReader:
    def __init__(self, read, image_base):
        self.read = read
        self.base = image_base
        self.profile_ok = None
        self.status = 'waiting for player'

    def _bytes(self, addr, size):
        if not 0x10000 <= addr < 0x800000000000:
            return None
        b = self.read(addr, size)
        return b if b is not None and len(b) == size else None

    def _number(self, addr, fmt):
        b = self._bytes(addr, struct.calcsize(fmt))
        return struct.unpack(fmt, b)[0] if b is not None else None

    def validate_profile(self):
        self.profile_ok = all(self._bytes(self.base + rva, len(code)) == code
                              for rva, code in SIGNATURES.items())
        return self.profile_ok

    def sample(self):
        if self.profile_ok is None:
            self.validate_profile()
        if not self.profile_ok:
            self.status = 'unsupported game code - tracking disabled'
            return None
        # Retry once when a load/update races our reads. Never retain a stale sample.
        for _ in range(2):
            result = self._sample_once()
            if result is not None:
                self.status = 'tracking native hero transform'
                return result
        return None

    def _sample_once(self):
        self.status = 'waiting for valid player transform'
        h = self._number(self.base + HERO_HANDLE_RVA, '<I')
        if h is None:
            return None
        index, generation = h & 0xFFFFF, (h >> 20) & 0x7FF
        if not generation:
            return None
        pool = self._number(self.base + ENTITY_POOL_RVA, '<Q')
        count = self._number(self.base + ENTITY_COUNT_RVA, '<I')
        if not pool or count is None or not index < count <= 0x100000:
            return None
        entity = pool + index * ENTITY_STRIDE
        entry = self._bytes(entity, 10)
        if entry is None or struct.unpack_from('<H', entry, 8)[0] != generation:
            return None
        transform = struct.unpack_from('<Q', entry)[0]
        raw = self._bytes(transform, 64)
        if raw is None:
            return None
        m = struct.unpack('<16f', raw)
        if not self._valid_transform(m):
            return None
        # The handle, pool allocation and entity generation/pointer must still refer
        # to the same object after reading its matrix (including slot reuse).
        if (self._number(self.base + HERO_HANDLE_RVA, '<I') != h
                or self._number(self.base + ENTITY_POOL_RVA, '<Q') != pool
                or self._number(self.base + ENTITY_COUNT_RVA, '<I') != count
                or self._bytes(entity, 10) != entry):
            return None
        return HeroSample(h, entity, transform, m[12:15],
                          math.degrees(math.atan2(m[10], m[8])))

    @staticmethod
    def _valid_transform(m):
        if not all(math.isfinite(v) for v in m):
            return False
        if abs(m[15] - 1) > 0.01 or any(abs(m[i]) > 0.01 for i in (3, 7, 11)):
            return False
        rows = [m[i:i + 3] for i in (0, 4, 8)]
        if any(not 0.8 < sum(v*v for v in row) < 1.2 for row in rows):
            return False
        if any(abs(sum(a*b for a, b in zip(rows[i], rows[j]))) > 0.15
               for i, j in ((0, 1), (0, 2), (1, 2))):
            return False
        return math.hypot(m[8], m[10]) > 0.01
