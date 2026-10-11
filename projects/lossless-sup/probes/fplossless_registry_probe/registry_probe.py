#!/usr/bin/env python3
"""Bounded offline execution of pinned fp V5.02 app-variable machine code.

NOT a loader, camera API, or proof that the original Lua/allocator works.
Only explicitly supplied firmware bytes are read. No device libraries imported.
"""
import hashlib
from pathlib import Path
import struct

from unicorn import (Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_PROT_READ,
                     UC_PROT_WRITE, UC_PROT_EXEC, UC_HOOK_CODE, UC_HOOK_MEM_WRITE)
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)

BASE = 0xC0000000
SEG0_SIZE = 49_245_696
SEG0_SHA256 = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"
REGISTER = 0xC05DB308
LOOKUP = 0xC05DB418
LOOKUP_APP = 0xC05DCA88
MAP_APPEND = 0xC05ED248
LUA_WRAPPER = 0xC05DB868
STRCMP = 0xC0013E2C
NATIVE = {
    "register": (REGISTER, 0xC05DB412),
    "registry_lookup": (LOOKUP, 0xC05DB42E),
    "app_lookup": (LOOKUP_APP, 0xC05DCAB6),
    "get_registry": (0xC05D9EB0, 0xC05D9EB8),
    "vector_append": (0xC05D74A8, 0xC05D74D2),
    "vector_get": (0xC05D7528, 0xC05D7530),
    "vector_grow": (0xC05D75B8, 0xC05D75E8),
    "map_reserve": (0xC05ED1F0, 0xC05ED246),
    "map_append": (MAP_APPEND, 0xC05ED294),
    "map_sort_key": (0xC05ED298, 0xC05ED2B0),
    "map_sort": (0xC05ED2B0, 0xC05ED3B8),
    "map_lookup": (0xC05ED3B8, 0xC05ED45A),
    "name_hash_fnv1a": (0xC05E9DE8, 0xC05E9E0A),
}
REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)


class ProbeError(RuntimeError):
    pass


def load_firmware(path):
    image = Path(path).read_bytes()
    validate_image(image)
    return image


def validate_image(image):
    if len(image) != SEG0_SIZE or hashlib.sha256(image).hexdigest() != SEG0_SHA256:
        raise ProbeError("firmware size/SHA-256 does not match pinned seg0")


class RegistryProbe:
    RAM = 0x10000000
    RAM_SIZE = 0x40000
    APP = RAM
    ROOT = RAM + 0x1000
    REGISTRY = ROOT + 0x60
    MAP = REGISTRY + 0x14
    ALLOCATOR = RAM + 0x2000
    DEFINITION = RAM + 0x3000
    NAME = RAM + 0x3100
    OUT = RAM + 0x3400
    SERVICES = 0x20000000
    ALLOC = SERVICES
    FREE = SERVICES + 0x10
    REALLOC = SERVICES + 0x20
    STOP = SERVICES + 0xFF0
    HEAP = RAM + 0x4000
    HEAP_END = RAM + 0x30000
    STACK = RAM + RAM_SIZE - 0x10
    MAX_INSTRUCTIONS = 20_000
    TIMEOUT_US = 250_000

    def __init__(self, image, vector_capacity=4, map_capacity=4):
        validate_image(image)
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        image_size = (len(image) + 0xFFF) & ~0xFFF
        self.uc.mem_map(BASE, image_size, UC_PROT_READ | UC_PROT_WRITE)
        self.uc.mem_write(BASE, image)
        self.uc.mem_protect(BASE, image_size, UC_PROT_READ | UC_PROT_EXEC)
        self.uc.mem_map(self.RAM, self.RAM_SIZE, UC_PROT_READ | UC_PROT_WRITE)
        self.uc.mem_map(self.SERVICES, 0x1000, UC_PROT_READ | UC_PROT_WRITE)
        self.uc.mem_write(self.SERVICES, b"\x70\x47" * 0x800)
        self.uc.mem_protect(self.SERVICES, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
        self.cursor = self.HEAP
        self.blocks = {}
        self.calls = []
        self.visited = set()
        self.writes = []
        self.lua_names = []
        self.lua_result = 0
        self.fail_allocation = set()
        self.allocation_calls = 0
        self.instructions = 0
        self.stopped = False
        self.write_words(self.APP + 0x888, self.ROOT)
        self.write_words(self.ALLOCATOR, self.ALLOC | 1, self.FREE | 1, self.REALLOC | 1)
        self.write_words(self.ALLOCATOR + 0x34, 0xA110CA7E)
        vector = self._allocate(vector_capacity * 4) if vector_capacity else 0
        entries = self._allocate(map_capacity * 12) if map_capacity else 0
        indices = self._allocate(map_capacity * 4) if map_capacity else 0
        self.write_words(self.REGISTRY, self.ALLOCATOR, 0, vector_capacity, 8, vector)
        self.write_words(self.MAP, self.ALLOCATOR, map_capacity, 0, entries, indices, 1)
        # A nonzero marker only: the original Lua state is NOT initialized/executed.
        self.write_words(self.REGISTRY + 0x48, self.RAM + 0x3500)
        self.uc.hook_add(UC_HOOK_CODE, self._instruction)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._native_write)

    def close(self):
        self.uc = None

    def write(self, address, data):
        if not self.RAM <= address <= address + len(data) <= self.RAM + self.RAM_SIZE:
            raise ProbeError("host stub write outside synthetic RAM")
        self.uc.mem_write(address, bytes(data))

    def write_words(self, address, *values):
        self.write(address, struct.pack("<%dI" % len(values), *values))

    def words(self, address, count=1):
        return struct.unpack("<%dI" % count, self.uc.mem_read(address, count * 4))

    def string(self, address):
        if not self.RAM <= address < self.RAM + self.RAM_SIZE:
            raise ProbeError("stub string pointer is outside synthetic RAM")
        data = bytes(self.uc.mem_read(address, min(128, self.RAM + self.RAM_SIZE - address)))
        end = data.find(b"\0")
        if end < 0:
            raise ProbeError("stub string exceeded 127-byte bound")
        return data[:end]

    def _allocate(self, size):
        if size <= 0 or self.cursor + size > self.HEAP_END:
            raise ProbeError("synthetic heap allocation bound exceeded")
        pointer = self.cursor
        self.cursor = (pointer + size + 15) & ~15
        self.blocks[pointer] = size
        self.write(pointer, b"\xA5" * size)
        return pointer

    def _return(self, value):
        self.uc.reg_write(UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def _instruction(self, uc, address, size, _):
        self.instructions += 1
        if address == self.STOP:
            self.stopped = True
            uc.emu_stop()
            return
        args = [uc.reg_read(reg) for reg in REGS]
        if address in (self.ALLOC, self.REALLOC, self.FREE, LUA_WRAPPER, STRCMP):
            self.calls.append({"address": "0x%08X" % address, "args": args,
                               "lr": "0x%08X" % uc.reg_read(UC_ARM_REG_LR)})
            if address in (self.ALLOC, self.REALLOC):
                self.allocation_calls += 1
                if self.allocation_calls in self.fail_allocation:
                    self._return(0)
                    return
                if address == self.ALLOC:
                    pointer = self._allocate(args[0])
                else:
                    if args[0] not in self.blocks:
                        raise ProbeError("realloc of unknown synthetic allocation")
                    old_size = self.blocks[args[0]]
                    pointer = self._allocate(args[1])
                    self.write(pointer, uc.mem_read(args[0], min(old_size, args[1])))
                    del self.blocks[args[0]]
                self._return(pointer)
            elif address == self.FREE:
                if args[0] not in self.blocks:
                    raise ProbeError("free of unknown synthetic allocation")
                del self.blocks[args[0]]
                self._return(0)
            elif address == LUA_WRAPPER:
                name = self.string(args[1]).decode("ascii")
                if self.lua_result == 0:
                    self.lua_names.append(name)
                self._return(self.lua_result)
            else:
                left, right = self.string(args[0]), self.string(args[1])
                self._return((left > right) - (left < right))
            return
        for name, (start, end) in NATIVE.items():
            if start <= address and address + size <= end:
                self.visited.add(name)
                return
        raise ProbeError("unknown external/native execution at 0x%08X" % address)

    def _native_write(self, uc, access, address, size, value, _):
        if not self.RAM <= address <= address + size <= self.RAM + self.RAM_SIZE:
            raise ProbeError("native write outside synthetic RAM: 0x%08X" % address)
        self.writes.append((address, size))

    def run(self, entry, *args, instruction_limit=None):
        if len(args) > 4:
            raise ProbeError("this harness does not infer stack-argument ABI")
        if entry & 1:
            raise ProbeError("supply even code address; harness explicitly sets Thumb +1")
        for reg, value in zip(REGS, (*args, 0, 0, 0, 0)):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM_REG_SP, self.STACK)
        self.uc.reg_write(UC_ARM_REG_LR, self.STOP | 1)
        self.instructions = 0
        self.stopped = False
        try:
            self.uc.emu_start(entry | 1, self.STOP + 2, timeout=self.TIMEOUT_US,
                              count=instruction_limit or self.MAX_INSTRUCTIONS)
        except UcError as exc:
            raise ProbeError("Unicorn rejected native execution: %s" % exc) from exc
        if not self.stopped:
            raise ProbeError("native instruction/time bound exhausted before return")
        if self.uc.reg_read(UC_ARM_REG_SP) != self.STACK:
            raise ProbeError("native call did not restore SP")
        return self.uc.reg_read(UC_ARM_REG_R0)

    def definition(self, name="MV_fpLossless", value=0, slot=0):
        name_address = self.NAME + slot * 0x80
        self.write(name_address, name.encode("ascii") + b"\0")
        self.write_words(self.DEFINITION, 0, name_address, value)
        return self.DEFINITION, name_address

    def register(self, name="MV_fpLossless", value=0, slot=0):
        definition, _ = self.definition(name, value, slot)
        return self.run(REGISTER, self.APP, 1, definition)

    def lookup(self, name="MV_fpLossless", app_wrapper=True):
        query = self.RAM + 0x3600
        self.write(query, name.encode("ascii") + b"\0")
        self.write_words(self.OUT, 0xDEADBEEF)
        status = self.run(LOOKUP_APP if app_wrapper else LOOKUP,
                          self.APP if app_wrapper else self.REGISTRY, query, self.OUT)
        return status, self.words(self.OUT)[0]

    def snapshot(self):
        vector = self.words(self.REGISTRY, 5)
        mapping = self.words(self.MAP, 6)
        return {"vector_count": vector[1], "vector_capacity": vector[2],
                "vector_pointer": vector[4], "map_capacity": mapping[1],
                "map_count": mapping[2], "map_entries": mapping[3],
                "map_indices": mapping[4], "map_sorted": mapping[5],
                "live_allocations": len(self.blocks), "lua_stub_names": self.lua_names[:]}
