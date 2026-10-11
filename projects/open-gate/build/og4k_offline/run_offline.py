#!/usr/bin/env python3
"""Run the complete OG4K offline suite; never open a camera transport.

Requires Python, clang and Unicorn. Missing dependencies or skipped native
checks are failures, never a partial camera-readiness success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
for directory in (HERE.parent, ROOT / "fpSup/opengate/og4k", HERE):
    sys.path.insert(0, str(directory))

TEST_MODULES = (
    "test_og4k_plan", "test_core", "test_core_review",
    "test_verify_frontend", "test_og4k_sizes",
    "test_verify_descriptor_native", "test_record_allocator", "test_pipeline",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    try:
        import unicorn
    except ImportError:
        parser.error("Unicorn is required: refusing to skip original-firmware execution")
    import core_build

    image = core_build.load_firmware()
    blob, _ = core_build.build()
    suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    passed = result.wasSuccessful() and not result.skipped
    print(json.dumps({
        "offline_suite_passed": passed,
        "tests_run": result.testsRun,
        "tests_skipped": len(result.skipped),
        "unicorn_version": unicorn.__version__,
        "firmware_sha256": hashlib.sha256(image).hexdigest(),
        "core_bytes": len(blob),
        "core_sha256": hashlib.sha256(blob).hexdigest(),
        "camera_accessed": False,
        "camera_ready": False,
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
