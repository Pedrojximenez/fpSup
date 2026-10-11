#!/usr/bin/env python3
"""Pinned, offline native page-boundary probe. No transport or deployable output."""
import importlib.util
from pathlib import Path
import struct

SHARED = Path(__file__).resolve().parents[2] / "research/ui/tools/native_variable_probe/registry_probe.py"
spec = importlib.util.spec_from_file_location("page_registry_support", SHARED)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)
from unicorn.arm_const import UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC

SELECT = 0xC05E82F0
PARSE = 0xC05E6400
NBU = 0xC18C0460
POOL = 0xC18C0474
MAINB2 = 0xC2030364
MAINB2_ENTRY = 0xC18EC77C
EXTRA_NATIVE = {
    "lazy_page_selector": (SELECT, 0xC05E83EC),
    "parser_scratch_cleanup": (0xC05E61F0, 0xC05E628C),
    "record_parser": (PARSE, 0xC05E7B28),
    "reader_byte": (0xC05E5D78, 0xC05E5D86),
    "reader_be32": (0xC05E5DB8, 0xC05E5DDE),
    "reader_seek": (0xC05E5EA8, 0xC05E5EB0),
    "string_pool_resolve": (0xC05E5B58, 0xC05E5B6C),
    "screen_constructor": (0xC05D9080, 0xC05D90B0),
    "screen_flag_set": (0xC05D9378, 0xC05D9390),
    "cache_publication": (0xC05D9A48, 0xC05D9A62),
    "root_retain": (0xC05CFAE0, 0xC05CFAE8),
}


class PageProbe(registry.RegistryProbe):
    SCREEN = registry.RegistryProbe.RAM + 0x800
    READER = registry.RegistryProbe.RAM + 0xA00
    TABLE = registry.RegistryProbe.RAM + 0xC00
    ROOT_OBJECT = registry.RegistryProbe.RAM + 0xD00
    INPUT = registry.RegistryProbe.RAM + 0xE00
    VTABLE = registry.RegistryProbe.RAM + 0xF00
    PREFLIGHT = registry.RegistryProbe.SERVICES + 0x100

    def __init__(self, image):
        self.image = image
        self.preflight_result = 1
        self.parse_script = None
        self.parse_events = []
        self.stub_events = []
        self.staged_screens = []
        self.arena_result = None
        super().__init__(image)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0x00F00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.write_words(self.APP, self.VTABLE)
        self.write_words(self.APP + 8, self.ALLOCATOR, 0xC2E00360)
        self.write_words(self.VTABLE + 12, self.PREFLIGHT | 1)
        self.write_words(self.SCREEN + 4, self.APP, POOL + 0x1A3B8, 0)
        self.write_words(self.SCREEN + 0x24, self.READER)
        self.write_words(self.READER, 0x01090000, 0, self.APP, 0)
        self.write_words(self.READER + 0x10, 176152, POOL, 0, 0)
        self.write_words(self.READER + 0x20, len(image) - (NBU - registry.BASE), NBU, 0)
        self.write_words(self.READER + 0x34, 0xC05E5D79, 0xC05E5DB9, 0, 0xC05E5EA9)
        self.write_words(self.READER + 0xA8, 1, self.TABLE)
        self.write_words(self.TABLE, 0xBDD26684, POOL + 0x1A3B8, MAINB2 - NBU)
        self.write_words(self.ROOT_OBJECT + 12, 1)
        self.write_words(self.READER + 0x54, self._allocate(16))

    def string(self, address):
        if registry.BASE <= address < registry.BASE + len(self.image):
            b = self.image[address - registry.BASE:address - registry.BASE + 128]
            if b.find(b"\0") < 0:
                raise registry.ProbeError("ROM string exceeds bound")
            return b.split(b"\0", 1)[0]
        return super().string(address)

    def _instruction(self, uc, address, size, data):
        args = [uc.reg_read(reg) for reg in registry.REGS]
        if address == PARSE and self.parse_script is not None:
            self.parse_events.append({"reader": args[0], "position": self.words(args[0] + 4)[0],
                                      "context": self.words(args[0] + 12)[0],
                                      "source": self.words(args[0] + 0x24)[0]})
            if not self.parse_script:
                raise registry.ProbeError("record stub sequence exhausted")
            result, objects, root = self.parse_script.pop(0)
            self.write_words(args[0] + 0x50, objects)
            self.write_words(args[0] + 0xB4, root)
            self.write_words(args[0] + 4, self.words(args[0] + 4)[0] + 8)
            self._return(result)
            return
        if address in (self.PREFLIGHT, 0xC05E8EF8, 0xC05E04E8, 0xC05E0CC8,
                       0xC05D9B00, 0xC05D3790, 0xC05CFAE8, 0xC05D9E88):
            self.stub_events.append({"address": hex(address), "args": args})
            result = 0
            if address == self.PREFLIGHT:
                result = self.preflight_result
            elif address == 0xC05E8EF8:
                result = self.ALLOCATOR if self.arena_result is None else self.arena_result
            elif address == 0xC05E0CC8:
                self.staged_screens.append(args[1])
            elif address == 0xC05CFAE8:
                self.write_words(args[0] + 12, self.words(args[0] + 12)[0] - 1)
            elif address == 0xC05D9E88:
                result = 32  # Synthetic component size, NOT native arena sizing evidence.
            self._return(result)
            return
        for name, (start, end) in EXTRA_NATIVE.items():
            if start <= address and address + size <= end:
                self.instructions += 1
                self.visited.add(name)
                return
        super()._instruction(uc, address, size, data)

    def select(self):
        return self.run(SELECT, self.APP, self.SCREEN)

    def parse(self, payload=None, position=None):
        self.parse_script = None
        if payload is not None:
            self.write(self.INPUT, payload)
            self.write_words(self.READER + 0x24, self.INPUT)
            self.write_words(self.READER + 4, 0)
        if position is not None:
            self.write_words(self.READER + 4, position)
        return self.run(PARSE, self.READER, instruction_limit=100_000)

    def single_mainb2_declaration(self):
        entry = self.image[MAINB2_ENTRY - registry.BASE:MAINB2_ENTRY - registry.BASE + 32]
        return struct.pack(">4I", 0x10001, 48, 171660, 1) + entry
