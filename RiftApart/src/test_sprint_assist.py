import struct
import unittest
import tempfile
from pathlib import Path
from sprint_assist import (SprintReader, SprintSample, SIGNATURES,
                           RUN_TYPE_RVA, SPRINT_OFFSET, RUN_LOCAL_CLASS, SprintGate, load_mode, save_mode,
                           load_hover_boots, save_settings, HoverToggle)
from test_player_tracking import Memory


class SprintReaderTests(unittest.TestCase):
    def setUp(self):
        self.m = Memory()
        self.table, self.ptr, self.vt = 0x400000000, 0x500000000, 0x600000000
        self.capacity = 8
        for r, code in SIGNATURES.items():
            self.m.put(self.m.base + r, code)
        self.m.pack(self.m.entity + 0x80, "<QH", self.table, self.capacity)
        self.m.put(self.table, bytes(self.capacity * 16))
        self.slot = ((self.m.base + RUN_TYPE_RVA) >> 4) & (self.capacity - 1)
        self.entry = self.table + 16 * self.slot
        self.m.pack(self.entry, "<QQ", self.m.base + RUN_TYPE_RVA, self.ptr)
        self.m.put(self.ptr, bytes(SPRINT_OFFSET + 1))
        self.m.pack(self.ptr, "<Q", self.vt)
        self.m.pack(self.ptr + 0x10, "<Q", self.m.entity)
        self.m.pack(self.vt + 0x100, "<Q", self.m.base + 0x7DEAF0)
        self.r = SprintReader(self.m.read, self.m.base)

    def test_native_sprint_flag_and_off(self):
        self.assertFalse(self.r.sample().sprinting)
        self.m.put(self.ptr + SPRINT_OFFSET, b"\x01")
        self.assertTrue(self.r.sample().sprinting)

    def test_animation_flag_can_be_off_while_toggle_is_on(self):
        self.m.put(self.ptr + 0x147, b"\x00")
        self.m.put(self.ptr + SPRINT_OFFSET, b"\x01")
        self.assertTrue(self.r.sample().sprinting)

    def test_reader_reports_plain_run_class(self):
        col, rva = 0x700000000, 0x123000
        self.m.pack(self.vt - 8, "<Q", col)
        self.m.put(col, struct.pack("<IIII", 1, 0, 0, rva))
        self.m.put(self.m.base + rva + 0x10, RUN_LOCAL_CLASS.encode() + bytes(64))
        self.assertTrue(self.r.sample().running)
        other = self.vt + 0x1000
        self.m.pack(self.ptr, "<Q", other)
        self.m.pack(other + 0x100, "<Q", self.m.base + 0x7DEAF0)
        self.m.pack(other - 8, "<Q", col + 0x100)
        self.m.put(col + 0x100, struct.pack("<IIII", 1, 0, 0, rva + 0x100))
        self.m.put(self.m.base + rva + 0x110, b".?AVHeroStateStrafeLocal@Hero@@" + bytes(64))
        self.assertFalse(self.r.sample().running)

    def test_hash_collision(self):
        entry = self.m.read(self.entry, 16)
        self.m.pack(self.entry, "<QQ", 123, 456)
        self.m.put(self.table + 16 * ((self.slot + 1) % self.capacity), entry)
        self.assertIsNotNone(self.r.sample())

    def test_missing_component(self):
        self.m.put(self.entry, bytes(16))
        self.assertIsNone(self.r.sample())

    def test_invalid_capacity(self):
        for cap in (0, 3, 8192):
            self.m.pack(self.m.entity + 0x88, "<H", cap)
            self.assertIsNone(self.r.sample())

    def test_full_table_missing_key_is_bounded(self):
        for i in range(self.capacity):
            self.m.pack(self.table + i * 16, "<QQ", 123, 456)
        self.assertIsNone(self.r.sample())

    def test_wrong_entity_owner(self):
        self.m.pack(self.ptr + 0x10, "<Q", self.m.entity + 0xC0)
        self.assertIsNone(self.r.sample())

    def test_unrecognized_subclass(self):
        self.m.pack(self.vt + 0x100, "<Q", self.m.base + 999)
        self.assertIsNone(self.r.sample())

    def test_corrupt_flag_and_short_read(self):
        self.m.put(self.ptr + SPRINT_OFFSET, b"\x02")
        self.assertIsNone(self.r.sample())
        self.r.hero.read = lambda addr, size: b"\0" * max(0, size - 1)
        self.assertIsNone(self.r.sample())

    def test_changed_game_code(self):
        self.m.put(self.m.base + 0x7DC590, b"\xCC")
        self.assertIsNone(self.r.sample())
        self.assertFalse(self.r.profile_ok)

    def test_component_replaced_during_read(self):
        original = self.m.read
        def racing_read(addr, size):
            result = original(addr, size)
            if addr == self.ptr and size == SPRINT_OFFSET + 1:
                self.m.pack(self.entry + 8, "<Q", self.ptr + 0x1000)
            return result
        self.r.hero.read = racing_read
        self.assertIsNone(self.r.sample())


class SprintModeTests(unittest.TestCase):
    on = SprintSample((7, 123), True)
    off = SprintSample((7, 123), False)

    def test_default_and_persisted_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "settings.json"
            self.assertEqual(load_mode(p), "always")
            save_mode("normal", p)
            self.assertEqual(load_mode(p), "normal")
            p.write_text("broken", encoding="utf-8")
            self.assertEqual(load_mode(p), "always")

    def test_fire_or_aim_cancels_in_both_modes(self):
        for mode in ("normal", "always"):
            for mouse in ("fire", "aim", "both"):
                with self.subTest(mode=mode, mouse=mouse):
                    g = SprintGate()
                    self.assertEqual(g.update(1, self.on, True, True, mode=mode), "cancel")
                    self.assertIsNone(g.update(2, self.off, True, True, moving=True, mode=mode))

    def test_always_restores_after_combat_release(self):
        g = SprintGate()
        self.assertEqual(g.update(1, self.on, True, True), "cancel")
        self.assertIsNone(g.update(1.4, self.off, False, True, moving=True))
        self.assertEqual(g.update(1.6, self.off, False, True, moving=True), "enable")
        self.assertIsNone(g.update(2, self.on, False, True, moving=True))

    def test_normal_never_auto_enables(self):
        g = SprintGate()
        for t in (1, 2, 4):
            self.assertIsNone(g.update(t, self.off, False, True, moving=True, mode="normal"))

    def test_restore_after_jump_dash_component_gap(self):
        g = SprintGate()
        self.assertIsNone(g.update(1, self.on, False, True, moving=True))
        self.assertIsNone(g.update(2, None, False, True, moving=True))
        self.assertIsNone(g.update(3, self.off, False, True, moving=True))
        self.assertEqual(g.update(3.2, self.off, False, True, moving=True), "enable")

    def test_unknown_menu_focus_and_idle_never_enable(self):
        for sample, allowed, moving in ((None, True, True), (self.off, False, True),
                                         (self.off, True, False)):
            g = SprintGate()
            for t in (1, 2):
                self.assertIsNone(g.update(t, sample, False, allowed, moving=moving))

    def test_shift_held_waits_and_cancel_preempts_enable_cooldown(self):
        g = SprintGate()
        g.update(1, self.off, False, True, moving=True)
        self.assertEqual(g.update(1.2, self.off, False, True, moving=True), "enable")
        self.assertIsNone(g.update(1.25, self.on, True, True, shift=True))
        self.assertEqual(g.update(1.3, self.on, True, True), "cancel")

    def test_ignored_input_retries_only_if_toggle_still_on(self):
        g = SprintGate()
        self.assertEqual(g.update(1, self.on, True, True), "cancel")
        self.assertIsNone(g.update(1.2, self.on, True, True))
        self.assertEqual(g.update(1.4, self.on, True, True), "cancel")
        self.assertIsNone(g.update(2, self.off, True, True))
        self.assertIsNone(g.update(3, None, True, True))

    def test_fire_lock_with_toggle_already_off_is_unstuck(self):
        # Game cleared the toggle on the fire press but keeps re-entering Run.
        run_off = SprintSample((7, 123), False, True)
        for mode in ("normal", "always"):
            with self.subTest(mode=mode):
                g = SprintGate()
                self.assertIsNone(g.update(1.00, run_off, True, True, moving=True, mode=mode))
                self.assertIsNone(g.update(1.04, run_off, True, True, moving=True, mode=mode))
                self.assertIsNone(g.update(1.05, self.off, True, True, moving=True, mode=mode))
                self.assertIsNone(g.update(1.06, run_off, True, True, moving=True, mode=mode))
                self.assertEqual(g.update(1.07, run_off, True, True, moving=True, mode=mode), "unstick")
                self.assertIsNone(g.update(1.10, run_off, True, True, moving=True, mode=mode))

    def test_normal_strafe_fire_and_first_run_frame_never_unstick(self):
        run_off = SprintSample((7, 123), False, True)
        g = SprintGate()
        self.assertIsNone(g.update(1.00, run_off, True, True, moving=True))
        self.assertIsNone(g.update(1.01, run_off, True, True, moving=True))
        self.assertIsNone(g.update(1.02, run_off, True, True, moving=True))
        for t in (1.05, 1.2, 1.5, 2.0):
            self.assertIsNone(g.update(t, self.off, True, True, moving=True))

    def test_unstick_waits_after_cancel_and_resets_on_release(self):
        run_off = SprintSample((7, 123), False, True)
        g = SprintGate()
        self.assertEqual(g.update(1.00, self.on, True, True, moving=True), "cancel")
        for t in (1.05, 1.1, 1.15, 1.2):
            self.assertIsNone(g.update(t, run_off, True, True, moving=True))
        self.assertEqual(g.update(1.31, run_off, True, True, moving=True), "unstick")
        g2 = SprintGate()
        g2.update(1.00, run_off, True, True, moving=True)
        g2.update(1.04, run_off, True, True, moving=True)
        g2.update(1.05, run_off, True, True, moving=True)
        self.assertIsNone(g2.update(1.06, run_off, False, True, moving=True))
        self.assertIsNone(g2.update(1.07, run_off, True, True, moving=True))

    def test_game_clearing_toggle_on_click_unsticks_immediately(self):
        for mode in ("normal", "always"):
            with self.subTest(mode=mode):
                g = SprintGate()
                self.assertIsNone(g.update(1.00, self.on, False, True, moving=True, mode=mode))
                self.assertEqual(g.update(1.01, self.off, True, True, moving=True, mode=mode), "unstick")
                # One-sample blip back on right after our Shift is not re-cancelled.
                self.assertIsNone(g.update(1.03, self.on, True, True, moving=True, mode=mode))
                self.assertIsNone(g.update(1.05, self.off, True, True, moving=True, mode=mode))

    def test_hover_boots_never_pulse_enable(self):
        # Hover only lasts while Shift is held; HoverToggle handles it, not tap pulses.
        run_off = SprintSample((7, 123), False, True, "run")
        g = SprintGate(hover_boots=True)
        for t in (1.0, 1.2, 1.5, 2.0):
            self.assertIsNone(g.update(t, run_off, False, True, moving=True))

    def test_hover_toggle_by_physical_shift(self):
        h = HoverToggle()
        self.assertFalse(h.want_hold(True, False))
        self.assertTrue(h.physical_key(True))           # tap: on
        self.assertFalse(h.want_hold(True, False))      # user still holds it: no injection
        h.physical_key(False)
        self.assertTrue(h.want_hold(True, False))       # released: we hold it from now
        h.holding = True
        self.assertTrue(h.physical_key(True))           # tap again: off
        h.physical_key(False)
        self.assertFalse(h.holding)
        self.assertFalse(h.want_hold(True, False))

    def test_hover_toggle_aim_pauses_and_menus_turn_off(self):
        h = HoverToggle()
        h.physical_key(True); h.physical_key(False)
        self.assertFalse(h.want_hold(True, True))       # aiming: let go
        self.assertTrue(h.want_hold(True, False))       # resumes after aiming
        self.assertFalse(h.want_hold(False, False))     # menu / focus loss: off
        self.assertFalse(h.want_hold(True, False))      # and stays off

    def test_hovering_counts_as_on_and_fire_cancels_it(self):
        hover_on = SprintSample((7, 123), True, False, "hover")
        g = SprintGate()
        for t in (1.0, 1.5, 2.0):
            self.assertIsNone(g.update(t, hover_on, False, True, moving=True))
        self.assertTrue(g.hover_boots)
        self.assertEqual(g.update(2.1, hover_on, True, True, moving=True), "cancel")

    def test_never_enable_while_grinding(self):
        grind_off = SprintSample((7, 123), False, False, "other")
        g = SprintGate()
        for t in (1.0, 1.5, 2.0, 3.0):
            self.assertIsNone(g.update(t, grind_off, False, True, moving=True))

    def test_hover_boots_setting_persists_with_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "settings.json"
            self.assertFalse(load_hover_boots(p))
            save_mode("normal", p)
            save_settings(p, hover_boots=True)
            self.assertTrue(load_hover_boots(p))
            self.assertEqual(load_mode(p), "normal")

    def test_skipped_unstick_stays_armed_for_next_poll(self):
        g = SprintGate()
        g.update(1.00, self.on, False, True, moving=True)
        self.assertEqual(g.update(1.01, self.off, True, True, moving=True), "unstick")
        g.not_sent(1.012)
        self.assertEqual(g.update(1.024, self.off, True, True, moving=True), "unstick")

    def test_our_cancel_does_not_also_unstick(self):
        g = SprintGate()
        g.update(1.00, self.on, False, True, moving=True)
        self.assertEqual(g.update(1.01, self.on, True, True, moving=True), "cancel")
        for t in (1.05, 1.2, 1.4, 1.8):
            self.assertIsNone(g.update(t, self.off, True, True, moving=True))

    def test_press_while_not_sprinting_is_not_armed(self):
        g = SprintGate()
        g.update(1.00, self.off, False, True, moving=False, mode="normal")
        for t in (1.01, 1.1, 1.5):
            self.assertIsNone(g.update(t, self.off, True, True, moving=True, mode="normal"))

    def test_short_off_flicker_does_not_enable(self):
        g = SprintGate()
        self.assertIsNone(g.update(1, self.off, False, True, moving=True))
        self.assertIsNone(g.update(1.05, self.on, False, True, moving=True))
        self.assertIsNone(g.update(1.1, self.off, False, True, moving=True))


class CombatInputTests(unittest.TestCase):
    def test_left_click_is_hover_boost_not_combat_in_auto_hover(self):
        from sprint_assist import SprintAssist

        class Keys:
            down = set()
            def held(self, vk):
                return vk in self.down
        keys = Keys()
        a = SprintAssist(lambda addr, size: None, 0x140000000, 0, lambda: True, input_device=keys)
        keys.down = {0x01}
        self.assertTrue(a._combat(False))
        self.assertFalse(a._combat(True))
        keys.down = {0x02}
        self.assertTrue(a._combat(True))


if __name__ == "__main__":
    unittest.main()
