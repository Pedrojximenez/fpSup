"""Offline integration tests for the non-deployable high-rate test bundle."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from . import af_batch
from . import build_publication
from . import build_sender
from . import build_test_bundle as bundle


LAB = dict(
    recorder_base=0x48050000,
    sender_base=0x48050400,
    state_base=0x48054000,
    records_base=0x48054080,
    # Deliberately 512-byte aligned but not 1,024-byte aligned: MPS governs
    # host reads, while the sender contract requires only 64-byte DMA alignment.
    dma_cpu_base=0x4805C200,
    dma_bus_base=0x0805C200,
    request_base=0x48064800,
    result_base=0x48064820,
    ops_base=0x48064840,
    nonce=0x13579BDF,
    capacity=7,
    max_packet_size=1024,
    veneer_base=0xC072FC00,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class TestBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="fp-af-offline-bundle-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.output = Path(cls.temp.name) / "bundle"
        cls.rom = build_publication.root() / "out/seg0_c0000000.bin"
        argv = ["--output", str(cls.output), "--rom", str(cls.rom)]
        for name, value in LAB.items():
            option = "--" + name.replace("_", "-")
            argv += [option, str(value) if name in ("capacity", "max_packet_size")
                     else hex(value)]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cls.return_code = bundle.main(argv)
        cls.cli_result = json.loads(stdout.getvalue())
        cls.manifest = json.loads((cls.output / "manifest.json").read_text())

    def test_cli_emits_complete_explicit_lab_model_bundle(self):
        expected = {
            "README.txt", "SHA256SUMS", "initial-capture.bin",
            "initial-records.bin", "initial-state.bin", "manifest.json",
            "publication.bin", "sender-core.S", "sender-core.bin", "veneer.bin",
        }
        self.assertEqual(self.return_code, 0)
        self.assertEqual({path.name for path in self.output.iterdir()}, expected)
        self.assertEqual(self.cli_result["label"], "NOT_AF_BETA")
        self.assertFalse(self.cli_result["deployment_ready"])
        self.assertFalse(self.cli_result["hardware_validated"])

        manifest = self.manifest
        self.assertEqual(manifest["schema"], bundle.BUNDLE_SCHEMA)
        self.assertEqual(manifest["label"], "NOT_AF_BETA")
        self.assertEqual(manifest["address_provenance"],
                         "explicit_unleased_lab_model_inputs")
        self.assertTrue(manifest["safety"]["offline_only"])
        for claim in ("deployment_ready", "hardware_validated", "af_beta",
                      "camera_installer_included", "usb_transport_included",
                      "ownership_verified", "dma_mapping_verified"):
            self.assertFalse(manifest["safety"][claim], claim)

        layout = {entry["name"]: entry for entry in manifest["layout"]}
        for name in ("recorder", "sender", "state", "records", "dma_frame",
                     "request", "result", "ops", "veneer"):
            self.assertIn(name, layout)
        expected_addresses = {
            "recorder": LAB["recorder_base"], "sender": LAB["sender_base"],
            "state": LAB["state_base"], "records": LAB["records_base"],
            "dma_frame": LAB["dma_cpu_base"], "request": LAB["request_base"],
            "result": LAB["result_base"], "ops": LAB["ops_base"],
            "veneer": LAB["veneer_base"],
        }
        self.assertEqual({name: layout[name]["address"] for name in expected_addresses},
                         expected_addresses)
        self.assertEqual(layout["dma_frame"]["alignment"], 64)
        self.assertEqual(LAB["dma_cpu_base"] % LAB["max_packet_size"], 512)
        self.assertEqual(manifest["transport"]["dma_bus_base"], LAB["dma_bus_base"])
        self.assertFalse(manifest["transport"]["dma_mapping_verified"])
        self.assertEqual(manifest["capture"]["nonce"], LAB["nonce"])
        self.assertEqual(manifest["capture"]["capacity"], LAB["capacity"])
        self.assertEqual(manifest["capture"]["records_bytes"],
                         LAB["capacity"] * af_batch.RECORD_BYTES)
        self.assertEqual(manifest["capture"]["batch_bytes"],
                         af_batch.BATCH_HEADER_BYTES + af_batch.HEADER_BYTES +
                         LAB["capacity"] * af_batch.RECORD_BYTES)
        self.assertEqual(manifest["capture"]["initial_capture_representation"],
                         "offline_concat_state_then_records_not_uploadable")

        warning = (self.output / "README.txt").read_text()
        self.assertIn("NOT AF BETA", warning)
        self.assertIn("NOT HARDWARE VALIDATED", warning)
        self.assertIn("NO CAMERA INSTALLER", warning)
        self.assertIn("not RAM leases", warning)

    def test_capture_sender_and_veneer_bytes_match_reused_builders(self):
        manifest = self.manifest
        capture = (self.output / "initial-capture.bin").read_bytes()
        state = (self.output / "initial-state.bin").read_bytes()
        records = (self.output / "initial-records.bin").read_bytes()
        self.assertEqual(capture, state + records)
        self.assertEqual(len(state), af_batch.HEADER_BYTES)
        self.assertEqual(len(records), LAB["capacity"] * af_batch.RECORD_BYTES)
        header = struct.unpack("<16I", state)
        self.assertEqual(header[:5], (af_batch.MAGIC, af_batch.SCHEMA,
                                     af_batch.RECORD_BYTES, LAB["capacity"],
                                     LAB["nonce"]))
        self.assertEqual(set(records), {0})
        publication = (self.output / "publication.bin").read_bytes()
        self.assertTrue(publication)
        self.assertEqual(digest(publication),
                         manifest["publication"]["code_sha256"])
        self.assertEqual(digest((self.output / "sender-core.bin").read_bytes()),
                         manifest["sender"]["code_sha256"])
        self.assertEqual(struct.unpack("<2I", (self.output / "veneer.bin").read_bytes()),
                         (0xE51FF004, LAB["recorder_base"]))
        self.assertEqual(manifest["firmware"]["candidate_branch_word"],
                         build_publication.branch_word(LAB["veneer_base"]))

    def test_every_emitted_payload_hash_and_sum_verifies(self):
        for name, identity in self.manifest["artifacts"].items():
            data = (self.output / name).read_bytes()
            self.assertEqual(len(data), identity["bytes"])
            self.assertEqual(digest(data), identity["sha256"])

        sums = {}
        for line in (self.output / "SHA256SUMS").read_text().splitlines():
            checksum, name = line.split("  ", 1)
            sums[name] = checksum
        expected = {path.name for path in self.output.iterdir()
                    if path.name != "SHA256SUMS"}
        self.assertEqual(set(sums), expected)
        for name, checksum in sums.items():
            self.assertEqual(digest((self.output / name).read_bytes()), checksum)

        source_files = {
            "bundle_builder_sha256": Path(bundle.__file__),
            "format_source_sha256": Path(af_batch.__file__),
            "publication_builder_sha256": Path(build_publication.__file__),
            "sender_builder_sha256": Path(build_sender.__file__),
        }
        for key, path in source_files.items():
            self.assertEqual(self.manifest["inputs"][key], digest(path.read_bytes()))
        self.assertEqual(self.manifest["firmware"]["rom_sha256"],
                         digest(self.rom.read_bytes()))

    def test_existing_output_is_refused_before_build_and_preserved(self):
        with tempfile.TemporaryDirectory(prefix="fp-af-no-overwrite-") as temp:
            output = Path(temp) / "existing"
            output.mkdir()
            sentinel = output / "sentinel"
            sentinel.write_bytes(b"keep")
            with mock.patch.object(bundle, "build_bundle") as build:
                with self.assertRaises(FileExistsError):
                    bundle.write_bundle(output, rom=self.rom, **LAB)
                build.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b"keep")
            self.assertEqual([path.name for path in output.iterdir()], ["sentinel"])

    def test_optional_veneer_can_be_omitted_only_for_direct_branch_layout(self):
        near = dict(LAB,
                    recorder_base=0xC0800000, sender_base=0xC0801000,
                    state_base=0xD0000000, records_base=0xD0000080,
                    dma_cpu_base=0xD0010200, dma_bus_base=0x10010200,
                    request_base=0xD0011000, result_base=0xD0011020,
                    ops_base=0xD0011040, veneer_base=None)
        artifacts, manifest = bundle.build_bundle(rom=self.rom, **near)
        self.assertNotIn("veneer.bin", artifacts)
        self.assertIsNone(manifest["publication"]["veneer_base"])
        self.assertEqual(manifest["publication"]["veneer_bytes"], 0)
        self.assertEqual(manifest["firmware"]["candidate_branch_word"],
                         build_publication.branch_word(near["recorder_base"]))

        far = dict(LAB, veneer_base=None)
        with self.assertRaisesRegex(ValueError, "BL alignment/range"):
            bundle.build_bundle(rom=self.rom, **far)

    def test_layout_overlap_and_64_byte_dma_alignment_are_rejected(self):
        overlap = dict(LAB, sender_base=LAB["recorder_base"])
        with self.assertRaisesRegex(ValueError, "overlaps"):
            bundle.build_bundle(rom=self.rom, **overlap)
        for key in ("dma_cpu_base", "dma_bus_base"):
            misaligned = dict(LAB, **{key: LAB[key] + 32})
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "(?i)dma.*alignment"):
                    bundle.build_bundle(rom=self.rom, **misaligned)

    def test_wrong_rom_identity_stops_before_output_creation(self):
        with tempfile.TemporaryDirectory(prefix="fp-af-wrong-rom-") as temp:
            root = Path(temp)
            rom = root / "wrong.bin"
            rom.write_bytes(b"not the audited ROM")
            output = root / "bundle"
            with self.assertRaisesRegex(ValueError, "unsupported ROM hash"):
                bundle.write_bundle(output, rom=rom, **LAB)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
