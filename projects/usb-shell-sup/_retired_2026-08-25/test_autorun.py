#!/usr/bin/env python3
import hashlib
import pathlib
import unittest

from build_compact_autorun import compact


ROOT = pathlib.Path(__file__).resolve().parent
REFERENCE = ROOT / "camera" / "AutoRun_v27_reference.txt"
PRODUCT = ROOT / "dist" / "AutoRun.txt"
REFERENCE_SHA256 = "40ee119a1ce0c5ac307a31045771d34033de88fcacf566b4105d9b0171b21d62"


def commands(text: str, prefix: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith(prefix)]


class CompactAutoRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reference_bytes = REFERENCE.read_bytes()
        cls.reference = cls.reference_bytes.decode("utf-8")
        cls.product = PRODUCT.read_text(encoding="utf-8")

    def test_reference_is_the_verified_v27_artifact(self) -> None:
        digest = hashlib.sha256(self.reference_bytes).hexdigest()
        self.assertEqual(digest, REFERENCE_SHA256)

    def test_product_is_reproducible(self) -> None:
        expected = "".join(compact(self.reference.splitlines(keepends=True), 200))
        self.assertEqual(self.product, expected)

    def test_all_ram_writes_and_handler_calls_are_preserved(self) -> None:
        self.assertEqual(commands(self.product, "mem set "), commands(self.reference, "mem set "))
        self.assertEqual(commands(self.product, "memmgr "), commands(self.reference, "memmgr "))
        self.assertEqual(commands(self.product, "log"), commands(self.reference, "log"))
        lines = self.product.splitlines()
        log_indexes = [index for index, line in enumerate(lines) if line == "log"]
        self.assertEqual(len(log_indexes), 29)
        self.assertTrue(all(lines[index + 1] == "ctrl sleep 200" for index in log_indexes))

    def test_diagnostics_are_removed_but_operator_cues_remain(self) -> None:
        self.assertNotIn("mem save ", self.product)
        self.assertEqual(commands(self.product, "display "), commands(self.reference, "display "))
        self.assertIn("ctrl sleep 30000", self.product)
        self.assertIn("ctrl sleep 20000", self.product)
        self.assertEqual(self.product.count("ctrl sleep 5000"), 3)
        self.assertLess(len(self.product.encode("utf-8")), len(self.reference_bytes))

    def test_critical_transport_constants_are_present(self) -> None:
        for line in (
            "mem set 0xC04DC618 0xEB092B07",
            "mem set 0xC31E38C8 0x00000002",
            "mem set 0xC30257B0 0xC072DF54",
            "mem set 0xC072E67C 0xC01E6D49",
            "mem set 0xC072E684 0xC01E6B81",
            "mem set 0xC072E6A8 0x27270707",
        ):
            self.assertIn(line, self.product)


if __name__ == "__main__":
    unittest.main(verbosity=2)
