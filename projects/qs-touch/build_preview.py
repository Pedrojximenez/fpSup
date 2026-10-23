#!/usr/bin/env python3
"""Assemble the local, self-contained interaction preview; no camera access."""
from pathlib import Path
import argparse
import base64

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--visualization", type=Path)
parser.add_argument("--qa", action="store_true", help="Build direct browser QA with opt-in motion trace")
args = parser.parse_args()
template = (root / "preview/qs-shell.html").read_text()
controller = (root / "preview/qs-controller.js").read_text()
motion = (root / "preview/qs-motion.js").read_text()
recording = (root / "preview/qs-recording.js").read_text()
assert controller.count("// QS_MOTION_CORE") == 1
controller = controller.replace("// QS_MOTION_CORE", motion)
assert controller.count("// QS_RECORDING_MODEL") == 1
controller = controller.replace("// QS_RECORDING_MODEL", recording)
assert template.count("<!-- QS_CONTROLLER -->") == 1
assert "</script" not in controller.lower()
fragment = template.replace("<!-- QS_CONTROLLER -->", "<script>\n" + controller + "\n</script>")
scene = root.parent / "open-gate/build/angle_fps_camera_20260915_verified_modes/fhd_qs2_iso800_2997_angle180_idle.jpg"
fragment = fragment.replace("__QS_SCENE__", "data:image/jpeg;base64," + base64.b64encode(scene.read_bytes()).decode("ascii"))
assert len(fragment.encode()) < 1_000_000
(root / "preview/fp-touch-qs.html").write_text(fragment)
if args.visualization:
    args.visualization.write_text(fragment)
if args.qa:
    wrapper = (root / "preview/qa-shell.html").read_text()
    checked = fragment.replace('<div id="fp-touch-qs"', '<div id="fp-touch-qs" data-qs-motion-check', 1)
    (root / "preview/qa-direct.html").write_text(wrapper.replace("<!-- QS_FRAGMENT -->", checked))
