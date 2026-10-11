#!/usr/bin/env python3
"""Execute fp V5.02 CinemaDNG recording allocation requests in project tests.

The original C037A990 kind-1 path, size-callback dispatch, RAW-size callback,
C001CFD8 handle wrapper and C0374180 handle cleanup execute unchanged. Only
external runtime services and the physical allocator/free operation are mocked.
Successful mock allocation does not establish available camera memory.
"""

from __future__ import annotations

import json
import struct

import og4k_sizes as sizes


ENTRY = 0xC037A990
FRAME_BYTES = 0x111C
DESCRIPTOR_BYTES = 0x48
CINEMADNG_KIND = 1
CINEMADNG_PREFIX = 0x15400  # Set in C0374268 kind-1 constructor path.
CORE_ALLOCATOR = 0xC001D038
MOCKS = {
    0xC03739C0: "available frame slots",
    0xC0021318: "RAW callback registry singleton address",
    0xC001CF78: "pool-10 singleton lookup",
    CORE_ALLOCATOR: "physical allocation and returned capacity",
    0xC03A9970: "secondary-buffer manager singleton",
    0xC03AB250: "secondary-buffer manager member lookup",
    0xC03AC290: "secondary-buffer demand decision",
    0xC001D3D0: "physical free operation",
}
NATIVE_CHAIN = (
    "C037A990 kind1", "C02DA770", "C02DA830", "C03D9630",
    "C03D9668", "C01AAA30 Thumb", "C0135D40 Thumb", "C0135DB8 Thumb",
    "C001CFD8", "C0374180 when secondary allocation fails",
)


def raw12_descriptor(width: int, height: int) -> bytes:
    """Synthetic descriptor: only fields consumed by C03D9630 are populated."""
    sizes.raw12_bytes(width, height)
    descriptor = bytearray(DESCRIPTOR_BYTES)
    struct.pack_into("<II", descriptor, 0, width, height)
    struct.pack_into("<I", descriptor, 0x20, 0)
    return bytes(descriptor)


class RecordAllocationEmulator(sizes.NativeSizing):
    FRAME = sizes.NativeSizing.RAM + 0x3000
    OWNER = sizes.NativeSizing.RAM + 0x5000
    REGISTRY = sizes.NativeSizing.RAM + 0x6000
    POOL = sizes.NativeSizing.RAM + 0x6100
    MANAGER = sizes.NativeSizing.RAM + 0x6200
    FAKE_PIXELS = 0x20000000  # Returned addresses are not backed by real memory.

    def __init__(self, image: bytes):
        super().__init__(image)
        self.uc.hook_add(self.unicorn.UC_HOOK_CODE, self._services)
        self.requests = []
        self.frees = []
        self.mock_calls = []

    def _r(self, register: int) -> int:
        return self.uc.reg_read(register)

    def _u32(self, address: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def _return(self, value: int):
        self.uc.reg_write(self.arm.UC_ARM_REG_R0, value)
        self.uc.reg_write(self.arm.UC_ARM_REG_PC, self._r(self.arm.UC_ARM_REG_LR))

    def _services(self, uc, address, size, data):
        if address not in MOCKS:
            return
        self.mock_calls.append(address)
        arm = self.arm
        r0, r1, r2, r3 = (self._r(reg) for reg in
                          (arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1,
                           arm.UC_ARM_REG_R2, arm.UC_ARM_REG_R3))
        if address == 0xC03739C0:
            self._return(self.available_slots)
        elif address == 0xC0021318:
            self._return(self.REGISTRY)
        elif address == 0xC001CF78:
            if r0 != 10:
                raise sizes.SizingError(f"unexpected pool selector {r0}")
            self._return(self.POOL)
        elif address == CORE_ALLOCATOR:
            index = len(self.requests)
            expected_handle = self.FRAME + (0x68 if index == 0 else 0x12C)
            if index > 1 or r0 != self.POOL or r3 != expected_handle + 4:
                raise sizes.SizingError("allocator destination differs from kind-1 handles")
            if r2 != 0x400:
                raise sizes.SizingError(f"allocator alignment differs from 0x400: {r2}")
            caller = self._u32(self._r(arm.UC_ARM_REG_SP))
            if caller != (0xC037AD2C if index == 0 else 0xC037ADD8):
                raise sizes.SizingError(f"unexpected allocator caller 0x{caller:08X}")
            succeeds = self.allocation_results[index] if index < len(self.allocation_results) else False
            pointer = self.FAKE_PIXELS + index * 0x02000000 if succeeds else 0
            # Model only the C001D038 API contract, not its pool algorithm.
            if succeeds:
                self.uc.mem_write(r3, struct.pack("<I", r1))
            self.requests.append({
                "pool": 10, "requested_bytes": r1, "alignment": r2,
                "handle_offset": expected_handle - self.FRAME,
                "wrapper_callsite": f"0x{caller - 4:08X}",
                "mock_success": succeeds, "mock_pointer": pointer,
                "mock_capacity": r1 if succeeds else None,
            })
            self._return(pointer)
        elif address == 0xC03A9970:
            self._return(self.MANAGER)
        elif address == 0xC03AB250:
            if r0 != self.MANAGER:
                raise sizes.SizingError("unexpected manager singleton")
            self._return(self.MANAGER)
        elif address == 0xC03AC290:
            if r0 != self.MANAGER:
                raise sizes.SizingError("unexpected secondary-buffer manager")
            self._return(int(self.secondary))
        elif address == 0xC001D3D0:
            if r0 != self.FRAME + 0x68:
                raise sizes.SizingError("unexpected release target")
            self.frees.append(tuple(struct.unpack("<3I", self.uc.mem_read(r0, 12))))
            self._return(0)

    def run(self, descriptor: bytes, *, prefix=CINEMADNG_PREFIX, secondary=False,
            allocation_results=(True,), available_slots=1, required_slots=1) -> dict:
        if len(descriptor) != DESCRIPTOR_BYTES:
            raise sizes.SizingError("recording descriptor must be exactly 0x48 bytes")
        width, height = struct.unpack_from("<II", descriptor)
        if struct.unpack_from("<I", descriptor, 0x20)[0] != 0:
            raise sizes.SizingError("this verifier covers only uncompressed RAW12 format 0")
        sizes.raw12_bytes(width, height)
        if not 0 <= prefix <= 0x100000:
            raise sizes.SizingError("prefix outside bounded offline fixture")
        self.available_slots, self.secondary = available_slots, secondary
        self.allocation_results = tuple(allocation_results)
        self.requests, self.frees, self.mock_calls = [], [], []
        frame = bytearray(FRAME_BYTES)
        struct.pack_into("<I", frame, 4, CINEMADNG_KIND)
        frame[0x10:0x58] = descriptor
        struct.pack_into("<I", frame, 0x128, prefix)
        struct.pack_into("<I", frame, 0x1C0, required_slots)
        # Stock empty handle template from C0B99880: {0, 0, pool sentinel15}.
        template = self.uc.mem_read(0xC0B99880, 12)
        frame[0x68:0x74] = template
        frame[0x12C:0x138] = template
        self.uc.mem_write(self.FRAME, bytes(frame))
        self.uc.mem_write(self.OWNER, bytes(0x100))
        self.uc.mem_write(self.REGISTRY, struct.pack("<I", 0xC03D9630))
        self.uc.mem_write(self.POOL, struct.pack("<I", 10))
        result = self._run(ENTRY, (self.OWNER, self.FRAME), writes=(
            (self.FRAME + 0x68, self.FRAME + 0x74),
            (self.FRAME + 0x12C, self.FRAME + 0x138),
        ))
        after = bytes(self.uc.mem_read(self.FRAME, FRAME_BYTES))
        for index, (before, value) in enumerate(zip(frame, after)):
            if before != value and not (0x68 <= index < 0x74 or 0x12C <= index < 0x138):
                raise sizes.SizingError(f"unexpected frame mutation at +0x{index:X}")
        return {
            "raster": (width, height), "prefix": prefix, "returned_pointer": result,
            "requests": list(self.requests), "released_handles": list(self.frees),
            "primary_handle": struct.unpack_from("<3I", after, 0x68),
            "secondary_handle": struct.unpack_from("<3I", after, 0x12C),
            "mocked_services_called": sorted({MOCKS[addr] for addr in self.mock_calls}),
        }


def verify() -> dict:
    native = RecordAllocationEmulator(sizes.load_firmware())
    cases = {}
    for label, raster in (("stock_uhd", (3856, 2170)), ("og4k", sizes.RASTER)):
        descriptor = raw12_descriptor(*raster)
        cases[label] = native.run(descriptor)
        expected = CINEMADNG_PREFIX + sizes.raw12_bytes(*raster)["write_payload_512"]
        if cases[label]["requests"][0]["requested_bytes"] != expected:
            raise sizes.SizingError(f"original allocator request mismatch for {label}")
    descriptor = raw12_descriptor(*sizes.RASTER)
    cases["og4k_primary_allocation_fails"] = native.run(descriptor, allocation_results=(False,))
    cases["og4k_secondary_allocation_fails"] = native.run(
        descriptor, secondary=True, allocation_results=(True, False))
    cases["og4k_secondary_allocation_succeeds"] = native.run(
        descriptor, secondary=True, allocation_results=(True, True))
    cases["og4k_no_frame_slots"] = native.run(descriptor, available_slots=0)
    return {
        "firmware_sha256": sizes.SHA256,
        "native_functions": NATIVE_CHAIN,
        "mocked_services": {f"0x{k:08X}": v for k, v in MOCKS.items()},
        "cases": cases,
        "limitations": [
            "physical pool availability, capacity and allocation outcomes are mocked",
            "descriptor fixture populates only width, height, and format consumed by the size callback",
            "kind1 and prefix0x15400 are firmware-derived fixture inputs; constructor path is not executed here",
            "this verifies allocator requests and failure control flow, not DMA writes, ring depth, or sustained recording",
        ],
        "camera_ready": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
