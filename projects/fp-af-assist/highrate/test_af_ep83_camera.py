"""Host checks for the pure EP83 camera-adapter contract; no device I/O."""

import ctypes as c
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

if __package__:
    from . import af_batch, ep83_host_session
else:
    import af_batch
    import ep83_host_session


U8 = c.c_uint8
U32 = c.c_uint32
I32 = c.c_int32
VP = c.c_void_p


class Result(c.Structure):
    _fields_ = [
        ("phase", U32), ("nonce", U32), ("batch_bytes", U32),
        ("batch_crc", U32), ("error", I32), ("platform_rc", I32),
        ("dma_may_be_owned", U32), ("dma_reclaimable", U32),
    ]


class WaitState(c.Structure):
    _fields_ = [
        ("phase", U32), ("reference", U32), ("observed", U32),
        ("kernel_rc", I32), ("quarantine", U32),
    ]


class Receipt(c.Structure):
    _fields_ = [
        ("wait_rc", I32), ("active", U32), ("owned_trb", U32),
        ("current_trb", U32), ("expected_bus", U32),
        ("requested_bytes", U32), ("word0", U32), ("word1", U32),
        ("word2", U32), ("word3", U32),
    ]


class Offsets(c.Structure):
    _fields_ = [(name, U32) for name in (
        "sender_preflight", "sender_publish", "sender_start", "sender_wait",
        "sender_completion", "native_start", "wait_clear_flags",
        "wait_critical_enter", "wait_critical_exit", "wait_interest_load",
        "wait_interest_store", "wait_irq_reenable", "wait_flags",
    )]


class Config(c.Structure):
    _fields_ = [
        ("magic", U32), ("schema", U32), ("bytes", U32),
        ("expected_pool_base", U32), ("code_base", U32),
        ("code_limit", U32), ("state_addr", U32), ("records_addr", U32),
        ("dma_cpu", U32), ("dma_bus", U32), ("dma_capacity", U32),
        ("config_addr", U32), ("private_addr", U32),
        ("expected_count", U32), ("wait_ms", U32), ("armed_nonce", U32),
        ("mapping_epoch", U32), ("owner_epoch", U32), ("expected_trb", U32),
        ("expected_idle_trb", U32 * 4), ("offsets", Offsets),
        ("reserved", U32 * 28),
    ]


class Private(c.Structure):
    _fields_ = [
        ("magic", U32), ("schema", U32), ("bytes", U32), ("phase", U32),
        ("consumed_nonce", U32), ("owner_epoch", U32),
        ("mapping_epoch", U32), ("last_error", I32), ("result", Result),
        ("wait_state", WaitState), ("receipt", Receipt),
        ("owned_trb", U32), ("requested_bytes", U32), ("reference", U32),
        ("wait_rc", I32), ("reserved", U32 * 29),
    ]


class Request(c.Structure):
    _fields_ = [
        ("state", VP), ("records", VP), ("dma_cpu", VP),
        ("records_bytes", U32), ("dma_capacity", U32), ("dma_bus", U32),
        ("nonce", U32), ("wait_ms", U32),
    ]


class Snapshot(c.Structure):
    _fields_ = [(name, U32) for name in (
        "publication_callsite", "native_sender_patch", "ctx3_default",
        "pool_base", "ctx3_mode", "ctx3_direction", "ctx3_endpoint",
        "ctx3_fourth", "usb_state", "dalepena_shadow",
        "dalepena_hardware", "active", "resource_index", "wait_interest",
        "event_flag_id", "irq_gate", "mode1_start_gate",
        "native_ptp_inflight", "core_status", "trb_pointer",
        "trb_bus_pointer", "trb_snapshot_valid",
    )] + [("trb", U32 * 4)]


class CameraAdapterPureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="fp-af-camera-pure-")
        cls.addClassCleanup(cls.temp.cleanup)
        here = Path(__file__).resolve().parent
        library = Path(cls.temp.name) / "camera.dylib"
        shared = ["-dynamiclib"] if sys.platform == "darwin" else ["-shared", "-fPIC"]
        subprocess.run([
            "clang", *shared, "-O2", "-std=c11", "-ffreestanding",
            "-fno-builtin", "-Wall", "-Wextra", "-Werror",
            *(str(here / name) for name in (
                "af_sender.c", "af_ep83_wait.c", "af_ep83_memory.c",
                "af_ep83_camera.c")),
            "-o", str(library),
        ], check=True, capture_output=True, text=True)
        cls.lib = c.CDLL(str(library))
        cls.lib.af_ep83_camera_validate_trigger.argtypes = [
            c.POINTER(U8), c.POINTER(U32), c.POINTER(U32), c.POINTER(U32)]
        cls.lib.af_ep83_camera_validate_trigger.restype = I32
        cls.lib.af_ep83_camera_make_synthetic.argtypes = [
            c.POINTER(U8), c.POINTER(U8), U32, U32]
        cls.lib.af_ep83_camera_snapshot_ok.argtypes = [
            c.POINTER(Config), c.POINTER(Private), c.POINTER(Request),
            c.POINTER(Snapshot)]
        cls.lib.af_ep83_camera_snapshot_ok.restype = I32

    def validate(self, frame):
        raw = (U8 * len(frame)).from_buffer_copy(frame)
        sequence = U32()
        nonce = U32()
        count = U32()
        rc = self.lib.af_ep83_camera_validate_trigger(
            raw, c.byref(sequence), c.byref(nonce), c.byref(count))
        return rc, sequence.value, nonce.value, count.value

    def test_trigger_wire_is_identical_to_host_codec(self):
        frame = ep83_host_session.encode_trigger_frame(
            sequence=0x10203, nonce=0xA0B0C0D0, count=7)
        self.assertEqual(self.validate(frame), (1, 0x10203, 0xA0B0C0D0, 7))

    def test_trigger_corruption_and_nonzero_padding_fail_closed(self):
        frame = bytearray(ep83_host_session.encode_trigger_frame(
            sequence=9, nonce=10, count=1))
        frame[30] ^= 1
        self.assertEqual(self.validate(frame)[0], 0)
        frame = bytearray(ep83_host_session.encode_trigger_frame(
            sequence=9, nonce=10, count=1))
        frame[63] = 1
        # Even after repairing the outer CRC, nonzero reserved padding fails.
        frame[16:20] = b"\0" * 4
        import zlib
        frame[16:20] = zlib.crc32(frame).to_bytes(4, "little")
        self.assertEqual(self.validate(frame)[0], 0)

    def test_synthetic_capture_is_committed_but_never_af_usable(self):
        nonce, count = 0x55667788, 3
        state = (U8 * 64)()
        records = (U8 * (count * 128))()
        self.lib.af_ep83_camera_make_synthetic(state, records, nonce, count)
        decoded = af_batch.decode_capture(
            bytes(state) + bytes(records), expected_nonce=nonce)
        self.assertEqual(decoded["count"], count)
        self.assertTrue(all(record["model"] == 0x53594E54
                            for record in decoded["records"]))
        self.assertTrue(all("unsupported_model" in record["context_issues"]
                            for record in decoded["records"]))
        self.assertFalse(decoded["usable_for_af_control"])
        self.assertFalse(decoded["usable_for_dfd"])

    @staticmethod
    def valid_snapshot_objects():
        pool = 0x44F6FE00
        config = Config()
        config.expected_pool_base = pool
        config.state_addr = pool + 0x54000
        config.records_addr = pool + 0x54080
        config.dma_cpu = pool + 0x5C400
        config.dma_bus = config.dma_cpu - 0x40000000
        config.dma_capacity = 0x8080
        config.expected_count = 2
        config.wait_ms = 100
        config.armed_nonce = 0xABCDEF01
        config.mapping_epoch = 3
        config.owner_epoch = 4
        config.expected_trb = 0x431E32F0
        private = Private()
        private.phase = 1
        private.consumed_nonce = config.armed_nonce
        private.mapping_epoch = config.mapping_epoch
        private.owner_epoch = config.owner_epoch
        request = Request(config.state_addr, config.records_addr,
                          config.dma_cpu, 2 * 128, config.dma_capacity,
                          config.dma_bus, config.armed_nonce, config.wait_ms)
        snapshot = Snapshot()
        snapshot.publication_callsite = 0xEB00485C
        snapshot.native_sender_patch = 0x47702000
        snapshot.ctx3_default = 1
        snapshot.pool_base = pool
        snapshot.ctx3_mode = 1
        snapshot.ctx3_direction = 1
        snapshot.ctx3_endpoint = 3
        snapshot.usb_state = 0
        snapshot.dalepena_shadow = 0x80
        snapshot.dalepena_hardware = 0x80
        snapshot.resource_index = 0x80808080
        snapshot.event_flag_id = 1
        snapshot.core_status = 0x10
        snapshot.trb_pointer = 0x431E32F0
        snapshot.trb_bus_pointer = 0x031E32F0
        snapshot.trb_snapshot_valid = 1
        return config, private, request, snapshot

    def test_snapshot_accepts_cold_boot_resource_sentinel(self):
        values = self.valid_snapshot_objects()
        self.assertEqual(self.lib.af_ep83_camera_snapshot_ok(
            *(c.byref(value) for value in values)), 1)

    def test_snapshot_rejects_each_critical_identity_change(self):
        for field, value in (
                ("publication_callsite", 0xEA000000),
                ("native_sender_patch", 0),
                ("ctx3_mode", 2),
                ("wait_interest", 0x100),
                ("event_flag_id", 0),
                ("irq_gate", 1),
                ("mode1_start_gate", 1),
                ("native_ptp_inflight", 1),
                ("core_status", 0),
                ("trb_pointer", 0x431E32E0),
                ("trb_bus_pointer", 0x031E32E0),
                ("trb_snapshot_valid", 0)):
            with self.subTest(field=field):
                values = self.valid_snapshot_objects()
                setattr(values[3], field, value)
                self.assertEqual(self.lib.af_ep83_camera_snapshot_ok(
                    *(c.byref(item) for item in values)), 0)

        values = self.valid_snapshot_objects()
        values[0].expected_idle_trb[3] = 1
        values[3].trb[3] = 1
        self.assertEqual(self.lib.af_ep83_camera_snapshot_ok(
            *(c.byref(item) for item in values)), 0)

    def test_struct_sizes_match_the_binary_templates(self):
        self.assertEqual(c.sizeof(Config), 256)
        self.assertEqual(c.sizeof(Private), 256)


if __name__ == "__main__":
    unittest.main()
