"""Strict execution of the original brightness routines in Unicorn, offline.

Only the final native command-sequence dispatcher is stubbed. Its input words
are captured, not sent to hardware. Original segment-1 command descriptors and
sequences are used; the selected runtime root and ready state are explicit.
"""
import struct

from firmware import COMMAND_OFFSETS, TABLE, TABLE_SIZE, guarded_table

# Thumb entrypoints and their exclusive code ends, from the stock image.
RANGES = ((0xC00FA2E0, 0xC00FA2FA), (0xC00FA300, 0xC00FA314),
          (0xC00FA4F0, 0xC00FA5CE), (0xC00FA940, 0xC00FAACE),
          (0xC0625F20, 0xC0625F64))
DISPATCH = 0xC00F4560
COARSE, FINE, HAL = 0xC00FA4F1, 0xC00FA941, 0xC0625F21
STATE = 0xC31D715C
CACHED_GROUP, CACHED_COARSE, CACHED_FINE = 0xC2EFED48, 0xC2EFED4C, 0xC2EFED50


class CameraModel:
    STACK, STOP = 0x10000000, 0x10100000
    PARAM = 0x11000000
    RUNTIME_ROOT = 0xC2EFF150
    COARSE_COMMANDS, FINE_COMMANDS = 0xC2EFF7E8, 0xC2EFF8B0

    def __init__(self, firmware, plan=None):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import arm_const
        self.reg = arm_const
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(0xC0000000, 0x04000000)
        for base, data in firmware.segments:
            self.uc.mem_write(base, data)
        # BSS and runtime fixtures are zeroed, not image-tail guesses.
        self.uc.mem_map(self.STACK, 0x10000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.mem_map(self.PARAM, 0x1000)
        self.initial_sp = self.STACK + 0xFFF0
        self.events = []
        self.writes = []
        self.reached_stop = False
        self.allowed = RANGES
        self.original_sequences = {base: firmware.read(base, 25 * 8)
                                   for base in (self.COARSE_COMMANDS, self.FINE_COMMANDS)}
        self.uc.hook_add(UC_HOOK_CODE, self._code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._write)
        # Native init selects this exact descriptor root (c00faf00).
        self.put32(0xC2EFECFC, self.RUNTIME_ROOT)
        self.put32(STATE, 2)  # native ready state in the modeled scenario
        if plan is not None:
            table = guarded_table(self.uc.mem_read(TABLE, TABLE_SIZE), plan)
            self.uc.mem_write(TABLE, table)

    def put32(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def u32(self, address):
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def _write(self, uc, access, address, size, value, data):
        if not self.STACK <= address < self.STACK + 0x10000:
            self.writes.append((address, size, value))
        if not (self.STACK <= address and address + size <= self.STACK + 0x10000 or
                any(address == base + offset and size == 4
                    for base in self.original_sequences for offset in COMMAND_OFFSETS) or
                address in (CACHED_GROUP, CACHED_COARSE, CACHED_FINE) and size == 4):
            raise AssertionError(f"unexpected firmware memory write {address:#x}+{size}")

    def _code(self, uc, address, size, data):
        if address == self.STOP:
            self.reached_stop = True
            uc.emu_stop()
            return
        if address == DISPATCH:
            args = [uc.reg_read(getattr(self.reg, f"UC_ARM_REG_R{n}")) for n in range(3)]
            if (args[0] not in self.original_sequences or args[1:] != [25, 0xC2EFECA8]):
                raise AssertionError(f"unexpected command dispatcher args {args}")
            sequence = bytes(uc.mem_read(args[0], args[1] * 8))
            original = self.original_sequences[args[0]]
            mutable = {i for offset in COMMAND_OFFSETS for i in range(offset, offset + 4)}
            if any(a != b for i, (a, b) in enumerate(zip(sequence, original)) if i not in mutable):
                raise AssertionError("native driver changed an unrelated command field")
            words = [self.u32(args[0] + offset) for offset in COMMAND_OFFSETS]
            self.events.append({"words": words, "bytes": [x & 255 for x in words]})
            lr = uc.reg_read(self.reg.UC_ARM_REG_LR)
            for n in (0, 1, 2, 3, 12):
                uc.reg_write(getattr(self.reg, f"UC_ARM_REG_R{n}"), 0xBAD00000 + n)
            uc.reg_write(self.reg.UC_ARM_REG_R0, 0)
            uc.reg_write(self.reg.UC_ARM_REG_PC, lr)
            return
        if not any(low <= address and address + size <= high for low, high in self.allowed):
            raise AssertionError(f"unapproved native execution {address:#x}")

    def run(self, kind, value, force=0):
        if kind not in ("coarse", "fine", "hal_fine"):
            raise ValueError("unknown emulation entry")
        self.events.clear()
        self.writes.clear()
        self.reached_stop = False
        saved = {}
        for n in range(4, 12):
            register = getattr(self.reg, f"UC_ARM_REG_R{n}")
            saved[register] = 0x55550000 + n
            self.uc.reg_write(register, saved[register])
        self.uc.reg_write(self.reg.UC_ARM_REG_SP, self.initial_sp)
        self.uc.reg_write(self.reg.UC_ARM_REG_LR, self.STOP)
        if kind == "coarse":
            # This native handler uses the low byte of its packed value.
            self.put32(self.PARAM + 8, value)
            entry, r0, r1 = COARSE, self.PARAM, 0
        elif kind == "hal_fine":
            self.put32(self.PARAM, 1)
            self.put32(self.PARAM + 4, value)
            entry, r0, r1 = HAL, self.PARAM, 0
        else:
            entry, r0, r1 = FINE, value, force
        self.uc.reg_write(self.reg.UC_ARM_REG_R0, r0 & 0xFFFFFFFF)
        self.uc.reg_write(self.reg.UC_ARM_REG_R1, r1)
        self.uc.emu_start(entry, self.STOP + 4, count=3000)
        if not self.reached_stop:
            raise AssertionError("native routine exceeded instruction budget")
        if self.uc.reg_read(self.reg.UC_ARM_REG_SP) != self.initial_sp:
            raise AssertionError("native routine did not restore SP")
        if any(self.uc.reg_read(r) != v for r, v in saved.items()):
            raise AssertionError("native routine damaged a callee-saved register")
        return {"return_u32": self.uc.reg_read(self.reg.UC_ARM_REG_R0),
                "dispatches": list(self.events), "writes": list(self.writes)}
