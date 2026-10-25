"""Exact-image, offline-only LCD brightness analysis for SIGMA fp 5.02.

No camera client, memory allocator, uploader, or device interface is imported.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEGMENTS = (
    (0xC0000000, 0x2EF6E00, "out/seg0_c0000000.bin",
     "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"),
    (0xC2EF6E00, 0x39A00, "out/seg1_c2ef6e00.bin",
     "0dcaca8f5441fe4ddc6ed801cb888e325df4e76006e4f53a1c3219809b22ce7b"),
)
TABLE = 0xC2EFED84
TABLE_SIZE = 42
PATCH_ADDRESS = 0xC2EFEDA6
COMMAND_OFFSETS = (0x2C, 0x4C, 0x6C, 0x94, 0x8C, 0xB4)
STOCK_TABLE = bytes([
    133, 133, 133, 133, 133, 255, 255,
    255, 255, 255, 255, 255, 255, 255,
    72, 72, 72, 72, 72, 72, 72,
    93, 93, 93, 93, 93, 89, 89,
    0, 0, 0, 0, 0, 47, 119,
    5, 25, 65, 130, 215, 255, 255,
])


class Firmware:
    def __init__(self, root=ROOT):
        self.segments = []
        self.identity = []
        for base, size, name, expected in SEGMENTS:
            data = (Path(root) / name).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if len(data) != size or digest != expected:
                raise ValueError(f"unsupported firmware image: {name}")
            self.segments.append((base, data))
            self.identity.append({"path": name, "base": hex(base),
                                  "size": size, "sha256": digest})

    def read(self, address, size):
        if size < 0:
            raise ValueError("negative read size")
        for base, data in self.segments:
            offset = address - base
            if 0 <= offset and offset + size <= len(data):
                return data[offset:offset + size]
        raise ValueError(f"read outside declared firmware segments: {address:#x}")

    def coarse(self, index):
        if not 0 <= index <= 6:
            raise ValueError("manual LCD index must be 0..6")
        return [self.read(TABLE + column * 7 + index, 1)[0]
                for column in range(6)]

    def fine(self, value, *, include_rejected_100=False):
        maximum = 100 if include_rejected_100 else 99
        if not 1 <= value <= maximum:
            raise ValueError(f"fine LCD table value must be 1..{maximum}")
        if value <= 51:
            return [*self.read(0xC07CAC90, 5),
                    self.read(0xC07CACA0 + value, 1)[0]]
        return [*self.read(0xC07CAC98, 4),
                self.read(0xC07CACD4 + value - 50, 1)[0],
                self.read(0xC07CAC9D, 1)[0]]


def make_plan(firmware):
    before = firmware.read(TABLE, TABLE_SIZE)
    source = firmware.coarse(6)
    target = firmware.fine(100, include_rejected_100=True)
    differences = [i for i, (a, b) in enumerate(zip(source, target)) if a != b]
    if differences != [4] or source[4] != 119 or target[4] != 122:
        raise ValueError("stock maximum and rejected fine-100 table relationship changed")
    if source != firmware.fine(99):
        raise ValueError("stock maximum does not equal native fine 99")
    after = bytearray(before)
    after[PATCH_ADDRESS - TABLE] = target[4]
    return {
        "schema": "fp-lcd-brightness-offline-plan-v1",
        "status": "offline_candidate_not_hardware_validated",
        "firmware": firmware.identity,
        "guard": {"address": hex(TABLE), "size": TABLE_SIZE,
                  "before_hex": before.hex(), "after_hex": bytes(after).hex()},
        "edits": [{"address": hex(PATCH_ADDRESS), "width": 1,
                   "before": source[4], "after": target[4]}],
        "stock_maximum_command_bytes": source,
        "candidate_maximum_command_bytes": target,
        "reference": "unused LUT entry for fine 100; rejected by the unmodified native driver",
        "rollback": "restore the exact 42-byte before-image only if the entire after-image matches",
        "deployment": "not included; no AutoRun, sup, device write, or camera operation",
        "measured_nits": None,
        "nits_gain_percent": None,
        "limits": [
            "Command data are not calibrated luminance, PWM duty, or LED current.",
            "Panel register meanings and physical effect of this change are unverified.",
            "Candidate exceeds the native accepted maximum; its hardware suitability is unknown.",
            "No native instruction/guard patch is emitted; the table candidate is experimental.",
            "A table edit alone may not refresh an already cached maximum setting.",
            "Automatic-mode scheduling and display-state transitions are not simulated.",
        ],
    }


def guarded_table(current, plan, *, restore=False):
    """Apply/undo to a local byte string; never reads or writes camera memory."""
    if plan.get("schema") != "fp-lcd-brightness-offline-plan-v1":
        raise ValueError("unsupported patch schema")
    guard = plan["guard"]
    if guard["address"] != hex(TABLE) or guard["size"] != TABLE_SIZE:
        raise ValueError("unexpected patch extent")
    before = bytes.fromhex(guard["before_hex"])
    after = bytes.fromhex(guard["after_hex"])
    if len(before) != TABLE_SIZE or len(after) != TABLE_SIZE:
        raise ValueError("incomplete table guard")
    if before != STOCK_TABLE:
        raise ValueError("plan before-image is not the supported stock table")
    changes = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    offset = PATCH_ADDRESS - TABLE
    if changes != [offset] or before[offset] != 119 or after[offset] != 122:
        raise ValueError("plan is not the bounded unused-LUT candidate")
    expected_edits = [{"address": hex(PATCH_ADDRESS), "width": 1,
                       "before": 119, "after": 122}]
    if plan.get("edits") != expected_edits:
        raise ValueError("edit list contradicts the guarded before/after images")
    expected, result = (after, before) if restore else (before, after)
    if bytes(current) != expected:
        raise ValueError("table ownership/before-image mismatch")
    return result
