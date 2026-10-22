#!/usr/bin/env python3
"""Original fp V5.02 A2P/P2A -> property storage -> key-event execution.

Offline only. Reuses the pinned strict registry/binding harness. Component
layouts/property declarations/vtables are native; the object lookup/active
framework, allocation, Lua, locks, timers and final UI dispatch are bounded
services. No page construction, renderer, GUI scheduling or camera is claimed.
The parent process isolates macOS Unicorn JIT failures from unittest discovery.
Use RegistryProbe's code/write guards, not BindingProbe's memory-read hook:
on this macOS Unicorn 2.1.4, that read hook corrupts Thumb ITEE state across the
native userdata getter. No native instructions are replaced to work around it.
"""
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location(
    "permission_shared_binding", HERE.parent / "native_variable_probe/binding_probe.py")
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)
registry = binding.registry
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
                               UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_S0)

IMAGE = ROOT / "out/seg0_c0000000.bin"
ATTACH = 0xC05E4670
A2P = 0xC05E3F60
KEY_EVENT = 0xC05FBFB8
SET_INT = 0xC05D63A8
SET_FLOAT = 0xC05D6878
NATIVE = {
    "a2p_lifecycle": (ATTACH, 0xC05E493E),
    "a2p_property_arity": (0xC05E3F00, 0xC05E3F12),
    "a2p_descriptor_lookup": (0xC05E3F18, 0xC05E3F5E),
    "a2p_set_property": (A2P, 0xC05E4288),
    "p2a_callback": (0xC05E4288, 0xC05E45E4),
    "a2p_variable_changed": (0xC05E45E8, 0xC05E466A),
    "event_kind": (0xC05E4E68, 0xC05E4E6C),
    "key_kind": (0xC05FC208, 0xC05FC20C),
    "value_kind": (0xC05FB080, 0xC05FB084),
    "property_enter": (0xC05D54C8, 0xC05D551A),
    "property_leave": (0xC05D5520, 0xC05D5534),
    "property_descriptor_storage_type": (0xC05D5670, 0xC05D56F2),
    "property_lookup": (0xC05D5FC8, 0xC05D6014),
    "property_descriptor": (0xC05D6018, 0xC05D6038),
    "integer_property_core": (0xC05D6038, 0xC05D6242),
    "integer_property_read": (0xC05D6248, 0xC05D633C),
    "integer_set_wrapper": (SET_INT, 0xC05D63D2),
    "integer_get_wrapper": (0xC05D6400, 0xC05D641C),
    "float_property_core": (0xC05D64E0, 0xC05D66EE),
    "float_property_read": (0xC05D66F0, 0xC05D680C),
    "float_set_wrapper": (SET_FLOAT, 0xC05D68A4),
    "float_get_wrapper": (0xC05D68D0, 0xC05D68EC),
    "string_get_wrapper": (0xC05D6F08, 0xC05D6FBC),
    "component_kind": (0xC05D6FC0, 0xC05D6FC6),
    "component_app": (0xC05D70E8, 0xC05D70FC),
    "component_userdata": (0xC05D7148, 0xC05D7160),
    "component_subscription": (0xC05D7240, 0xC05D72FC),
    "component_notify": (0xC05D7300, 0xC05D737C),
    "component_subscribe_wrapper": (0xC05D7380, 0xC05D7386),
    "vector_init_append": (0xC05D7708, 0xC05D7726),
    "callback_array_append": (0xC05D9C28, 0xC05D9CDC),
    "callback_array_get": (0xC05D9CE0, 0xC05D9CEA),
    "callback_array_count": (0xC05D9D18, 0xC05D9D1C),
    "callback_array_copy": (0xC05D9D48, 0xC05D9D5C),
    "app_active": (0xC05DAEC8, 0xC05DAEDC),
    "event_owner": (0xC05E9318, 0xC05E9338),
    "key_event": (KEY_EVENT, 0xC05FC126),
    "control_value_callback": (0xC05FAD48, 0xC05FB018),
    "control_value_compare": (0xC06012D0, 0xC0601400),
}
SERVICES = {
    0xC05D0288: "owner_attach_active",
    0xC05D0240: "owner_variable_active",
    0xC05D1928: "owner_component_lookup",
    0xC05E9550: "timer",
    0xC05E93A8: "final_action_dispatch",
    0xC05E9440: "held_key_count",
    0xC05E9468: "held_key_at",
    0xC0601140: "control_value_property_sync",
    0xC05FA998: "control_value_event",
    0xC06011F0: "small_integer_normalization",
    0xC0015058: "memset",
}
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


def check(ok, message):
    if not ok:
        raise AssertionError(message)


class PermissionProbe(registry.RegistryProbe):
    """Native component fields; only framework services below are simulated."""
    ASSIGNMENT = binding.BindingProbe.ASSIGNMENT
    def __init__(self, image, cursor=False, binding_type=0, keycode=13):
        self.dispatches = []
        self.service_calls = []
        self.native_pcs = set()
        self.cursor_target = cursor
        self.keycode = keycode
        super().__init__(image)
        self.write_words(self.APP + 8, self.ALLOCATOR)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.write_words(self.APP + 0x840, 1)
        self.write(self.NAME, b"MV_fpLosslessCursor\0" if cursor else b"MV_fpLosslessConfirm\0")
        name = self.string(self.NAME).decode("ascii")
        check(self.register(name=name) == 0, "private registration failed")
        check(self.run(registry.LOOKUP_APP, self.APP, self.NAME, self.OUT) == 0,
              "private lookup failed")
        self.descriptor = self.words(self.OUT)[0]
        check(self.register(name="MV_fpLossless", value=1, slot=1) == 0,
              "saved value registration failed")
        check(self.run(registry.LOOKUP_APP, self.APP, self.NAME + 0x80, self.OUT) == 0,
              "saved value lookup failed")
        self.saved_descriptor = self.words(self.OUT)[0]
        self.owner = self.zero(0x100)
        self.container = self.zero(0x40)
        self.write_words(self.container, self.APP)
        self.property_name = self.zero(16)
        self.write(self.property_name, b"value\0" if cursor else b"type\0")
        check(keycode in (39, 13), "only pinned donor Right/Enter keys are modeled")
        self.target_id = 3 if cursor else (10 if keycode == 39 else 12)
        if cursor:
            self.target, self.storage, self.userdata, self.callbacks = self.component(
                0xC2E02918, 0xC2E027C8, [0, 0x3F800000, 0, 1, 1])
            self.write_words(self.userdata + 0x14, 0, 0x3F800000, 0, 0)
            self.write_words(self.userdata + 0x2C, 1, 1)
        else:
            self.target, self.storage, self.userdata, self.callbacks = self.component(
                0xC2E02DE4, 0xC2E02D14, [0, 2, 1, keycode, 0])
        self.event, self.event_storage, self.event_data, _ = self.component(
            0xC2E00180, 0xC2E000A0,
            [binding_type, self.NAME, self.target_id, self.property_name, 0, 6])
        self.write_words(self.event + 0x24, self.owner)
        self.write_words(self.event_data + 4, 0xFFFFFFFF)
        self.message = self.zero(0x20)
        self.handled = self.zero(4)

    def zero(self, size):
        address = self._allocate(size)
        self.write(address, bytes(size))
        return address

    def component(self, plugin, declarations, values):
        component = self.zero(0x40)
        offsets = self.zero(2 * len(values))
        storage = self.zero(16 * len(values))
        userdata = self.zero(0x40)
        callbacks = self.zero(0x18)
        entries = self.zero(4 * 12)
        self.write_words(callbacks, self.ALLOCATOR, 12, 0, 4, 0, entries)
        self.write_words(component, self.container)
        self.write_words(component + 0x10, plugin, len(values), declarations,
                         offsets, storage, 0, callbacks)
        self.write_words(component + 0x34, userdata)
        self.write(offsets, struct.pack("<%dH" % len(values),
                                        *(index * 4 for index in range(len(values)))))
        for index, value in enumerate(values):
            self.write_words(storage + index * 16, value, value, 16, 0)
        return component, storage, userdata, callbacks

    def string(self, address):
        # Native property-name declarations are immutable ROM, private names RAM.
        if registry.BASE <= address < registry.BASE + registry.SEG0_SIZE:
            data = bytes(self.uc.mem_read(address, 128))
            end = data.find(b"\0")
            check(end >= 0, "native name exceeds bound")
            return data[:end]
        return super().string(address)

    def _instruction(self, uc, address, size, data):
        if address in SERVICES:
            self.instructions += 1
            args = [uc.reg_read(reg) for reg in registry.REGS]
            self.service_calls.append((address, tuple(args)))
            if address in (0xC05D0288, 0xC05D0240):
                check(args[0] == self.owner, "unknown owner")
                self._return(1)
            elif address == 0xC05D1928:
                check(args[:2] == [self.owner, self.target_id], "unknown component lookup")
                self.write_words(args[2], self.target)
                self._return(0)
            elif address == 0xC05E93A8:
                check(args[0] == self.target and args[1] == self.message,
                      "unexpected final dispatcher object")
                self.dispatches.append(tuple(args))
                self._return(0)
            elif address == 0xC05E9440:
                check(args[0] == self.target, "wrong held-key owner")
                self.write_words(args[1], 1)
                self._return(0)
            elif address == 0xC05E9468:
                check(args[:2] == [self.target, 0], "unknown held-key query")
                self.write_words(args[2], self.keycode)
                self._return(0)
            elif address == 0xC0015058:
                self.write(args[0], bytes([args[1] & 255]) * args[2])
                self._return(args[0])
            elif address == 0xC06011F0:
                value = struct.unpack("<f", uc.mem_read(args[0], 4))[0]
                check(value in (-1.0, 0.0, 1.0, 2.0), "unmodeled normalization")
                self._return(0)
            else:
                check(args[0] == self.target, "unknown timer/controlValue object")
                self._return(0)
            return
        for name, (start, end) in NATIVE.items():
            if start <= address and address + size <= end:
                self.instructions += 1
                self.visited.add(name)
                self.native_pcs.add(address)
                return
        for name, (start, end) in binding.EXTRA_NATIVE.items():
            if start <= address and address + size <= end:
                self.instructions += 1
                self.visited.add(name)
                return
        super()._instruction(uc, address, size, data)

    def run(self, entry, *args, instruction_limit=None):
        sentinels = [0x44000000 + i * 0x01010101 for i in range(len(SAVED))]
        for reg, value in zip(SAVED, sentinels):
            self.uc.reg_write(reg, value)
        result = super().run(entry, *args, instruction_limit=instruction_limit)
        check([self.uc.reg_read(reg) for reg in SAVED] == sentinels,
              "native call did not preserve r4-r11")
        return result

    def attach(self):
        self.write_words(self.message + 8, 0x2416)
        return self.run(ATTACH, self.event, self.message, 0, self.handled)

    def press(self, phase=0):
        before = len(self.dispatches)
        self.write_words(self.message, 0x40, 0, self.keycode)
        check(self.run(KEY_EVENT, self.target, self.message, phase, self.handled) == 0,
              "key handler failed")
        return len(self.dispatches) - before

    def set_float(self, value):
        self.uc.reg_write(UC_ARM_REG_S0, struct.unpack("<I", struct.pack("<f", value))[0])
        return self.run(SET_FLOAT, self.target, 2)

    def set_integer(self, value):
        return binding.BindingProbe.set_integer(self, value)


class NativeCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = registry.load_firmware(IMAGE)

    def probe(self, **kwargs):
        p = PermissionProbe(self.image, **kwargs)
        self.addCleanup(p.close)
        return p

    def test_a2p_permission_changes_real_storage_and_confirmation(self):
        # Donor ListItem: local10 Right(args=39), local12 Enter(args=13).
        for keycode in (39, 13):
            with self.subTest(keycode=keycode):
                p = self.probe(keycode=keycode)
                self.assertEqual(p.attach(), 0)
                vector = p.words(p.descriptor + 0x10)[0]
                self.assertEqual(p.words(vector + 4)[0], 1)
                self.assertEqual(p.words(p.words(vector + 0x10)[0])[0], p.event)
                self.assertEqual(p.words(p.callbacks + 8)[0], 0)
                self.assertEqual(p.words(p.event_data + 0x1C)[0], 0)
                self.assertEqual(p.press(), 0)
                for enabled in (1, 0, 1, 0):
                    self.assertEqual(p.set_integer(enabled), 0)
                    self.assertEqual(p.words(p.storage)[0], enabled)
                    self.assertEqual(p.press(), enabled)
                    self.assertEqual(p.words(p.saved_descriptor + 8)[0], 1)
                self.assertIn(A2P, p.native_pcs)
                self.assertIn(0xC05D6038, p.native_pcs)
                self.assertIn(0xC05D61DC, p.native_pcs)
                self.assertTrue(all(item[3] == 0x2500 for item in p.dispatches))

    def test_read_only_permission_has_no_reverse_write(self):
        p = self.probe()
        self.assertEqual(p.attach(), 0)
        self.assertEqual(p.run(SET_INT, p.target, 0, 1), 0)
        self.assertEqual(p.words(p.storage)[0], 1)
        self.assertEqual(p.words(p.descriptor + 8)[0], 0)
        self.assertEqual(p.words(p.callbacks + 8)[0], 0)
        self.assertNotIn(0xC05E4288, p.native_pcs)
        self.assertEqual(p.words(p.saved_descriptor + 8)[0], 1)

    def test_cursor_type_one_registers_and_runs_reverse_callback(self):
        p = self.probe(cursor=True, binding_type=1)
        self.assertEqual(p.attach(), 0)
        self.assertEqual(p.words(p.event_data + 0x1C)[0], 0xC05E4289)
        self.assertEqual(p.words(p.callbacks + 8)[0], 1)
        entry = p.words(p.callbacks + 0x14)[0]
        self.assertEqual(p.words(entry, 3), (0xC05E4289, 0, p.event_data))
        self.assertEqual(p.set_float(1.0), 0)
        self.assertEqual(p.words(p.storage + 2 * 16)[0], 0x3F800000)
        self.assertEqual(p.words(p.userdata + 0x1C)[0], 0x3F800000)
        self.assertEqual(p.words(p.descriptor + 8)[0], 1)
        self.assertEqual(p.words(p.saved_descriptor + 8)[0], 1)
        self.assertEqual(p.words(p.storage + 16)[0], 0x3F800000)
        self.assertIn(0xC05E4288, p.native_pcs)
        self.assertIn(0xC05D64E0, p.native_pcs)
        for value in (0, 1, 0):
            self.assertEqual(p.set_float(float(value)), 0)
            self.assertEqual(p.words(p.descriptor + 8)[0], value)
            self.assertEqual(p.words(p.saved_descriptor + 8)[0], 1)
            self.assertEqual(p.words(p.storage)[0], 0)  # Never lower list max to 0.
            self.assertEqual(p.words(p.storage + 16)[0], 0x3F800000)

    def test_zero_permission_does_not_drain_pending_repeat(self):
        p = self.probe()
        self.assertEqual(p.attach(), 0)
        self.assertEqual(p.words(p.storage)[0], 0)
        self.assertEqual(p.press(), 0)
        self.assertEqual(p.press(phase=3), 1)
        self.assertEqual(p.words(p.saved_descriptor + 8)[0], 1)

    def test_storage_write_mutation_is_caught(self):
        p = self.probe()
        self.assertEqual(p.attach(), 0)
        address = 0xC05D61DC
        self.assertEqual(bytes(p.uc.mem_read(address, 4)), bytes.fromhex("46f82030"))
        # Private emulator memory only: erase the ACTUAL property write.
        p.uc.mem_write(address, bytes.fromhex("00bf00bf"))
        self.assertEqual(p.set_integer(1), 0)  # A success flag alone is insufficient.
        self.assertEqual(p.words(p.descriptor + 8)[0], 1)
        self.assertEqual(p.words(p.storage)[0], 0)
        self.assertEqual(p.press(), 0)
        with self.assertRaises(AssertionError):
            self.assertEqual(p.words(p.storage)[0], 1)

    def test_unknown_execution_is_refused(self):
        p = self.probe()
        with self.assertRaisesRegex(registry.ProbeError, "unknown external/native"):
            p.run(0xC05D6000 - 0x1000)


class PermissionBindingARM(unittest.TestCase):
    def test_original_instruction_worker(self):
        command = [sys.executable, "-B"]
        if sys.flags.optimize:
            command.append("-O")
        command += [str(Path(__file__).resolve()), "--worker"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0,
                         "Offline ARM worker failed (JIT may require approved host execution).\n"
                         + result.stdout + result.stderr)
        self.assertIn("Ran 6 tests", result.stderr)
        self.assertNotIn("skipped", result.stderr)


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(PermissionBindingARM)


if __name__ == "__main__":
    if "--worker" in sys.argv:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeCases)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    unittest.main()
