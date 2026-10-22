#!/usr/bin/env python3
"""Offline execution of the fp Ver.5.02 NBU record interpreter, FUN_c05e6400.

This runs the camera's OWN interpreter over NBU bytes on the host, so a modified
record can be parsed and the resulting construction calls inspected before a card
is ever written.  Nothing here talks to a camera, and nothing outside the pinned
firmware image is executed.

What is real (original firmware instructions, executed):

    0xC05E6400..0xC05E7B28   the record interpreter itself
    0xC05E5D78               the four in-memory reader methods the context
    0xC05E5DB8               constructor installs at ctx+0x34..0x40: signed byte,
    0xC05E5E38               BIG-ENDIAN u32, block copy, and skip-n.  All of them
    0xC05E5EA8               only move the cursor at ctx+0x04 over the base at
                             ctx+0x24
    0xC05E5E20               the same word reinterpreted as a float
    0xC05E5B58               pool offset -> string: bounds-checks against the
                             pool size at ctx+0x10 and adds the base at ctx+0x14
    0xC05E5F20 / 0xC05E5FE0  the context constructors
    0xC05E63E8               the version/prologue reader
    0xC0013E2C               strcmp

Everything else is a Python stub that records its arguments, and any call to an
address that is neither allowed nor stubbed raises UnstubbedCall naming it -- so
"which firmware services does this record need" is an ANSWER, not a silent zero.

What this cannot tell you: whether the GUI draws the result, when a screen is
parsed, or what the stubbed firmware routines would really have done.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from pathlib import Path

from unicorn import (UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_THUMB, UC_PROT_EXEC,
                     UC_PROT_READ, UC_PROT_WRITE, Uc, UcError)
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_LR,
                               UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1,
                               UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP)

BASE = 0xC0000000
SEG0_SIZE = 49_245_696
SEG0_SHA256 = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"

INTERPRETER = (0xC05E6400, 0xC05E7B28)
CTX_CTOR = 0xC05E5FE0
CTX_CTOR_BASE = 0xC05E5F20
PROLOGUE = 0xC05E63E8
READ_BYTE = 0xC05E5D78
READ_WORD = 0xC05E5DB8
READ_BYTES = 0xC05E5E38
SKIP = 0xC05E5EA8
READ_FLOAT = 0xC05E5E20
POOL_STRING = 0xC05E5B58
STRCMP = 0xC0013E2C
DTOR_MARKER = 0xC05E6029          # what the stock caller writes to ctx+0x44

# Original instructions we are content to execute as they are.  Each range is a
# whole function; nothing here writes outside the context or reads I/O.
REAL = {
    "interpreter": INTERPRETER,
    "ctx_ctor": (CTX_CTOR, 0xC05E600A),
    "ctx_ctor_base": (CTX_CTOR_BASE, 0xC05E5FB0),
    "prologue": (PROLOGUE, 0xC05E6400),
    "read_byte": (READ_BYTE, 0xC05E5D86),
    "read_word": (READ_WORD, 0xC05E5DDE),
    "read_bytes": (READ_BYTES, 0xC05E5E80),
    "skip": (SKIP, 0xC05E5EB0),
    "read_float": (READ_FLOAT, 0xC05E5E32),
    "pool_string": (POOL_STRING, 0xC05E5B6C),
    "strcmp": (STRCMP, 0xC0013F00),
}

NAMES = {
    0xC05E8EF8: "alloc_from_context",
    0xC05E5B58: "pool_string",
    0xC05EDC40: "element_new",
    0xC05EDB68: "element_set_name",
    0xC05EDB10: "element_release",
    0xC05EDD20: "element_set_keys",
    0xC05E2988: "image_container_new",
    0xC05E2CA8: "container_append",
    0xC05DB308: "var_registry_register",
    0xC05DB198: "var_registry_init",
    0xC05D9EB0: "get_var_registry",
    0xC05DFE88: "find_resource",
    0xC05D8618: "resource_new",
    0xC05D87C8: "resource_add_field",
    0xC05D8A90: "resource_finish",
    0xC05E7B60: "reader_seek",
    0xC05E7B28: "reader_skip",
}


class ProbeError(RuntimeError):
    pass


class UnstubbedCall(ProbeError):
    def __init__(self, address: int) -> None:
        name = NAMES.get(address, "unknown")
        super().__init__(
            f"the interpreter called 0x{address:08X} ({name}); it is neither in "
            f"REAL nor stubbed. Add a stub deliberately -- do not let the real "
            f"routine run by accident."
        )
        self.address = address


@dataclass
class Call:
    name: str
    address: int
    args: tuple
    returned: int = 0


@dataclass
class Trace:
    """One FUN_c05e6400 call: the tokens it ate and what it did with them."""
    index: int
    cursor_in: int
    cursor_out: int = 0
    token: int = 0
    result: int = 0
    tokens: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    strings: list = field(default_factory=list)

    @property
    def consumed(self) -> int:
        return self.cursor_out - self.cursor_in


def load_firmware(path) -> bytes:
    image = Path(path).read_bytes()
    if len(image) != SEG0_SIZE or hashlib.sha256(image).hexdigest() != SEG0_SHA256:
        raise ProbeError(f"{path} is not the pinned seg0 image")
    return image


def nbu(*words: int, magic: bytes = b"NBU\x00", version: int = 0x01090000) -> bytes:
    """Build a little NBU container: magic, version, one spare word, then tokens.

    The stock caller sets the cursor to 4 and the prologue reads two words, so
    the first record token is the third word -- exactly as in the real container.
    """
    return magic + struct.pack(">I", version) + struct.pack(">I", 0) + \
        b"".join(struct.pack(">I", w & 0xFFFFFFFF) for w in words)


class NbuProbe:
    RAM = 0x10000000
    RAM_SIZE = 0x200000
    APP = RAM + 0x0000
    ROOT = RAM + 0x1000
    ALLOCATOR = RAM + 0x2000
    CTX = RAM + 0x3000
    DESCRIPTOR = RAM + 0x3200
    OWNER = RAM + 0x3300          # ctx+0x0C: the set's owner; +0x0C holds its arena
    BLOB = RAM + 0x4000               # where a synthetic container is placed
    BLOB_MAX = 0x40000
    HEAP = RAM + 0x80000
    HEAP_END = RAM + 0x1F0000
    STACK = RAM + RAM_SIZE - 0x100
    SERVICES = 0x20000000
    STOP = SERVICES + 0xFF0
    MAX_INSTRUCTIONS = 2_000_000
    TIMEOUT_US = 5_000_000

    def __init__(self, image: bytes) -> None:
        if len(image) != SEG0_SIZE:
            raise ProbeError("firmware image has the wrong size")
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        size = (len(image) + 0xFFF) & ~0xFFF
        self.uc.mem_map(BASE, size, UC_PROT_READ | UC_PROT_WRITE)
        self.uc.mem_write(BASE, image)
        self.uc.mem_protect(BASE, size, UC_PROT_READ | UC_PROT_EXEC)
        self.uc.mem_map(self.RAM, self.RAM_SIZE, UC_PROT_READ | UC_PROT_WRITE)
        self.uc.mem_map(self.SERVICES, 0x1000, UC_PROT_READ | UC_PROT_WRITE)
        self.uc.mem_write(self.SERVICES, b"\x70\x47" * 0x800)   # bx lr, everywhere
        self.uc.mem_protect(self.SERVICES, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
        # The interpreter opens with `vpush {d8, d9}` and reads float tokens, so
        # VFP has to be on or unicorn rejects the first instruction.
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0x00F00000)   # cp10/cp11 full access
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)     # FPEXC.EN

        self.stock = image
        self.cursor = self.HEAP
        self.blocks: dict[int, int] = {}
        self.stubs: dict = {}
        self.allowed: dict = {}
        self.traces: list[Trace] = []
        self.calls: list[Call] = []
        self.stopped = False
        self.instructions = 0
        self._trace: Trace | None = None
        self.alloc_fail_after: int | None = None
        self.allocations = 0
        # Survey mode answers "which firmware services does this record need"
        # instead of stopping at the first one.  It is a discovery aid: every
        # auto-stub returns 0, which is NOT what the real routine would do.
        self.survey = False
        self.discovered: dict[int, int] = {}
        self._index: list | None = None
        self._pool: tuple | None = None

        self.ALLOC = self.SERVICES + 0x100
        self.FREE = self.SERVICES + 0x110
        self.REALLOC = self.SERVICES + 0x120
        self.write_words(self.ALLOCATOR, self.ALLOC | 1, self.FREE | 1, self.REALLOC | 1)
        self.write_words(self.ALLOCATOR + 0x34, 0xA110CA7E)
        # Fields of the app object the interpreter reaches through ctx+0x08.
        # Each one is here because an instruction in FUN_c05e6400 reads it; the
        # citation is the instruction, not a guess.
        self.write_words(self.APP + 0x08, self.ALLOCATOR)    # 0xC05E8F00
        self.write_words(self.APP + 0x60, self.ALLOCATOR)    # 0xC05E776E, then [r0]/[r0+0x34]
        self.write_words(self.APP + 0x888, self.ROOT)        # 0xC05E6880 etc.
        self.uc.hook_add(UC_HOOK_CODE, self._instruction)

    # --- memory helpers ---------------------------------------------------

    def write(self, address: int, data: bytes) -> None:
        if not self.RAM <= address <= address + len(data) <= self.RAM + self.RAM_SIZE:
            raise ProbeError("host write outside synthetic RAM")
        self.uc.mem_write(address, bytes(data))

    def write_words(self, address: int, *values: int) -> None:
        self.write(address, struct.pack("<%dI" % len(values), *[v & 0xFFFFFFFF for v in values]))

    def words(self, address: int, count: int = 1) -> tuple:
        return struct.unpack("<%dI" % count, self.uc.mem_read(address, count * 4))

    def string(self, address: int, limit: int = 128) -> str | None:
        """Read a NUL-terminated string from anywhere mapped (pool included)."""
        try:
            raw = bytes(self.uc.mem_read(address, limit))
        except UcError:
            return None
        end = raw.find(b"\0")
        if end < 0:
            return None
        try:
            return raw[:end].decode("ascii")
        except UnicodeDecodeError:
            return None

    def _allocate(self, size: int) -> int:
        self.allocations += 1
        if self.alloc_fail_after is not None and self.allocations > self.alloc_fail_after:
            return 0
        if size <= 0 or self.cursor + size > self.HEAP_END:
            raise ProbeError("synthetic heap exhausted")
        pointer = self.cursor
        self.cursor = (pointer + size + 15) & ~15
        self.blocks[pointer] = size
        self.write(pointer, b"\0" * size)
        return pointer

    # --- stubbing ---------------------------------------------------------

    def allow(self, lo: int, hi: int, name: str) -> None:
        """Execute this whole firmware range for real instead of stubbing it.

        Use it for pure code (resource lookups, containers, string work).  Any
        unmapped access still stops the run, and every write outside synthetic
        RAM or the image is still caught by unicorn -- but a routine allowed here
        does whatever the firmware does, including things this harness does not
        model.  Name what you allowed and why in the test.
        """
        self.allowed[(lo, hi)] = name

    def stub(self, address: int, name: str | None = None, ret: int = 0,
             handler=None) -> None:
        """Serve this firmware address from Python.

        `handler(probe, args) -> int` gets the four argument registers and
        returns r0; without one the stub records the call and returns `ret`.
        """
        self.stubs[address] = (name or NAMES.get(address, f"stub_{address:08X}"),
                               ret, handler)

    def stub_all_known(self, **kwargs) -> None:
        """Stub every named firmware call the interpreter can reach, so a run
        gets all the way through and reports the whole call sequence."""
        for address in NAMES:
            if address in self.stubs:
                continue
            if any(lo <= address < hi for lo, hi in
                   list(REAL.values()) + list(self.allowed)):
                continue
            self.stub(address, **kwargs)

    def install_arena(self) -> None:
        """The one stub a run cannot do without.

        FUN_c05e8ef8(ctx, size) does not return raw memory: the caller
        immediately does `ldr r2,[r0]` / `ldr r1,[r0,#0x34]` / `blx r2`, so what
        comes back is an ALLOCATOR OBJECT carved out of those bytes -- alloc
        function at +0x00, tag at +0x34, like every other allocator here.  A stub
        that returns plain zeroed memory makes the interpreter branch to 0.

        This substitute gives back a block of `size` bytes with that header
        written into it, so sub-allocations arrive at the harness's own alloc
        stub.  The original arena's placement and bookkeeping are NOT reproduced.
        """
        def arena(probe: "NbuProbe", args: tuple) -> int:
            size = max(args[1], 0x40)
            pointer = probe._allocate(size)
            if pointer:
                probe.write_words(pointer, probe.ALLOC | 1, probe.FREE | 1,
                                  probe.REALLOC | 1)
                probe.write_words(pointer + 0x34, 0xA5E4A5E4)
            return pointer
        self.stub(0xC05E8EF8, "alloc_from_context", handler=arena)

    def _return(self, value: int) -> None:
        self.uc.reg_write(UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def _instruction(self, uc, address, size, _user):
        self.instructions += 1
        if address == self.STOP:
            self.stopped = True
            uc.emu_stop()
            return
        args = tuple(uc.reg_read(r) for r in
                     (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        if address in (self.ALLOC, self.REALLOC, self.FREE):
            if address == self.FREE:
                self.blocks.pop(args[0], None)
                result = 0
            elif address == self.ALLOC:
                result = self._allocate(args[0])
            else:
                old = self.blocks.pop(args[0], 0)
                result = self._allocate(args[1])
                if old:
                    self.write(result, uc.mem_read(args[0], min(old, args[1])))
            self._record("alloc" if address == self.ALLOC else
                         "free" if address == self.FREE else "realloc", address, args, result)
            self._return(result)
            return
        if address in self.stubs:
            name, ret, handler = self.stubs[address]
            result = handler(self, args) if handler else ret
            self._record(name, address, args, result)
            self._return(result)
            return
        for lo, hi in list(REAL.values()) + list(self.allowed):
            if lo <= address < hi:
                if address == READ_WORD and self._trace is not None:
                    self._trace.tokens.append(self._peek_token(args[0]))
                if address == POOL_STRING and self._trace is not None:
                    self._trace.calls.append(Call("pool_string", address, args))
                return
        if self.survey:
            self.discovered[address] = self.discovered.get(address, 0) + 1
            self.stub(address)
            name, ret, handler = self.stubs[address]
            self._record(name, address, args, ret)
            self._return(ret)
            return
        raise UnstubbedCall(address)

    def _peek_token(self, ctx: int) -> int:
        cursor, base = self.words(ctx + 4)[0], self.words(ctx + 0x24)[0]
        try:
            return struct.unpack(">I", self.uc.mem_read(base + cursor, 4))[0]
        except UcError:
            return -1

    def _record(self, name: str, address: int, args: tuple, result: int) -> None:
        call = Call(name, address, args, result)
        self.calls.append(call)
        if self._trace is not None:
            self._trace.calls.append(call)

    # --- running ----------------------------------------------------------

    def _call(self, entry: int, *args: int, limit: int | None = None) -> int:
        if entry & 1:
            raise ProbeError("pass an even address; the harness sets the Thumb bit")
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                              (*args, 0, 0, 0, 0)):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM_REG_SP, self.STACK)
        self.uc.reg_write(UC_ARM_REG_LR, self.STOP | 1)
        self.stopped = False
        try:
            self.uc.emu_start(entry | 1, self.STOP + 2, timeout=self.TIMEOUT_US,
                              count=limit or self.MAX_INSTRUCTIONS)
        except UcError as exc:
            pc = self.uc.reg_read(UC_ARM_REG_PC)
            raise ProbeError(f"unicorn stopped at 0x{pc:08X}: {exc}") from exc
        if not self.stopped:
            raise ProbeError("instruction/time bound reached before the call returned")
        if self.uc.reg_read(UC_ARM_REG_SP) != self.STACK:
            raise ProbeError("the call did not restore SP")
        return self.uc.reg_read(UC_ARM_REG_R0)

    NBU_BASE = 0xC18C0460
    NBU_SIZE = 0x1500000          # covers the whole record area from the base

    def index(self) -> list:
        """Parse the top-level NBU container and return its resource-set index.

        The container holds exactly two records: the string pool (tag 1) and the
        set table (tag 0x10001).  Each row is {fnv hash, name, byte offset from
        0xC18C0460}, 0x2C bytes, sorted by hash.  Verified: MainB2 comes back
        with hash BDD26684, pool offset 0x1A3B8 and offset 0x76FF04 -- the three
        values MAINB2_ROW_EXTENSION.md derived by hand from the image.
        """
        if self._index is not None:
            return self._index
        self.open(base=self.NBU_BASE, size=self.NBU_SIZE)
        first, second = self.record(), self.record()
        if (first.token, second.token) != (1, 0x10001):
            raise ProbeError(f"unexpected top-level tags {first.token:#x}, {second.token:#x}")
        self._pool = self.pool()
        count, array = self.ctx(0x2A)[0], self.ctx(0x2B)[0]
        rows = []
        for i in range(count):
            fnv, name, offset = self.words(array + i * 0x2C, 3)
            rows.append({"name": self.string(name), "hash": fnv, "offset": offset,
                         "address": self.NBU_BASE + offset,
                         "pool_offset": name - self._pool[1]})
        self._index = rows
        return rows

    OBJECT_FACTORY = (0xC05CF808, 0xC05CF9E8)

    def map_set(self, name: str, limit: int = 8000) -> list:
        """Walk a whole resource set and return every record's exact extent.

        This is the ground truth an authoring tool needs: the camera's own
        interpreter decides where each record ends, so the boundaries are not a
        guess.  On MainB2 it returns 1392 records and the last cursor lands
        exactly on MainB3's address -- the two numbers the hand analysis gives.
        """
        self.allow(*self.OBJECT_FACTORY, "object factory: allocates the object "
                   "from the owner arena (0xC05CF828)")
        self.survey = True
        base = self.open_set(name)
        address = [r for r in self.index() if r["name"] == name][0]["address"]
        out = []
        while len(out) < limit:
            trace = self.record()
            out.append({"index": trace.index, "tag": trace.token,
                        "address": address + trace.cursor_in,
                        "offset": trace.cursor_in, "size": trace.consumed,
                        "result": trace.result})
            if trace.result:
                return out
        raise ProbeError(f"{name} did not terminate within {limit} records")

    def open_set(self, name: str) -> int:
        """Open the resource set of that name, with the pool the top level set.

        A set is NOT a nested NBU container: it has no magic, the first token is
        at offset 0, and the version is inherited from the parent context rather
        than read -- so the harness writes it, and says so.
        """
        rows = self.index()
        for row in rows:
            if row["name"] == name:
                return self.open(base=row["address"], size=self.NBU_SIZE,
                                 magic=False, cursor=0, pool=self._pool, owner=True)
        raise ProbeError(f"no resource set named {name!r} in the emulated index")

    def open(self, blob: bytes | None = None, base: int | None = None,
             size: int | None = None, magic: bool = True, cursor: int = 4,
             version: int = 0x01090000, pool: tuple | None = None,
             owner: bool = False) -> int:
        """Build a parse context the way the stock caller does, over `blob`
        (placed in synthetic RAM) or over `base`/`size` already in memory."""
        if blob is not None:
            if base is not None:
                raise ProbeError("pass either blob or base, not both")
            if len(blob) > self.BLOB_MAX:
                raise ProbeError("synthetic container too large")
            self.write(self.BLOB, blob)
            base, size = self.BLOB, len(blob)
        if base is None or not size:
            raise ProbeError("a memory source needs a base and a nonzero size")
        if magic and bytes(self.uc.mem_read(base, 4)) != b"NBU\x00":
            raise ProbeError("source does not start with the NBU magic")
        self.write(self.CTX, b"\0" * 0xB8)
        # descriptor: [0] size (nonzero selects the in-memory reader), [4] base
        self.write_words(self.DESCRIPTOR, size, base, 0, 0, 0)
        if self._call(CTX_CTOR, self.CTX, self.APP, self.DESCRIPTOR, 0) != 0:
            raise ProbeError("the firmware context constructor refused the source")
        self.write_words(self.CTX + 0x44, DTOR_MARKER)
        self.write_words(self.CTX + 0x04, 4)
        for offset in (0x50, 0x54, 0xA4, 0xA8, 0xAC, 0xB0, 0xB4):
            self.write_words(self.CTX + offset, 0)
        if magic:
            consumed = self._call(PROLOGUE, self.CTX)
            if consumed != 8:
                raise ProbeError(f"the prologue consumed {consumed} bytes, expected 8")
        else:
            self.write_words(self.CTX, version)     # inherited, not read
            self.write_words(self.CTX + 0x04, cursor)
        if pool is not None:
            self.write_words(self.CTX + 0x10, pool[0])
            self.write_words(self.CTX + 0x14, pool[1])
        if owner:
            # A resource set is parsed with an owner object at ctx+0x0C whose
            # +0x0C holds the arena; the interpreter stores the arena it creates
            # there (0xC05E68EA).  Zero means "no owner", and the page tags then
            # write through a null pointer.
            self.write(self.OWNER, b"\0" * 0x40)
            self.write_words(self.CTX + 0x0C, self.OWNER)
        self.traces = []
        return self.words(self.CTX)[0]                       # the version word

    def record(self) -> Trace:
        """Run FUN_c05e6400 once: one record."""
        trace = Trace(index=len(self.traces), cursor_in=self.words(self.CTX + 4)[0])
        trace.token = self._peek_token(self.CTX)
        self._trace = trace
        try:
            trace.result = self._call(INTERPRETER[0], self.CTX)
        finally:
            self._trace = None
            trace.cursor_out = self.words(self.CTX + 4)[0]
            for call in trace.calls:
                if call.name == "pool_string":
                    text = self.pool_string(call.args[1])
                    if text is not None:
                        trace.strings.append(text)
            self.traces.append(trace)
        return trace

    def records(self, limit: int = 32) -> list[Trace]:
        out = []
        for _ in range(limit):
            trace = self.record()
            out.append(trace)
            if trace.result != 0:
                break
        return out

    # --- independent decoders --------------------------------------------

    def be_words(self, address: int, count: int) -> tuple:
        """Read big-endian words straight out of memory, without the firmware."""
        return struct.unpack(">%dI" % count, self.uc.mem_read(address, count * 4))

    def allocation_header(self, address: int | None = None) -> dict:
        """Decode a tag-0x10002 record in Python, so it can be compared with
        what the firmware's own parse of the same bytes produced.

        Layout, from MainB2 (3028 bytes = 757 big-endian words, all of which the
        interpreter reads):

            +0x00  tag        0x00010002
            +0x04  size       the whole record, 0xBD4 for MainB2
            +0x08  objects    0xC1
            +0x0C  0
            +0x10  classes    0x17
            then `classes` pairs of {name pool offset, instance count}
        """
        address = address if address is not None else self.words(self.CTX + 0x24)[0]
        tag, size, objects, spare, classes = self.be_words(address, 5)
        if tag != 0x00010002:
            raise ProbeError(f"0x{address:08X} is not an allocation header (tag {tag:#x})")
        pairs = self.be_words(address + 0x14, classes * 2)
        return {"size": size, "objects": objects, "spare": spare,
                "classes": [(self.pool_string(pairs[i * 2]), pairs[i * 2 + 1])
                            for i in range(classes)]}

    # --- reading the parsed state ----------------------------------------

    def pool(self) -> tuple[int, int]:
        """(pool size, pool base) as the interpreter established them."""
        return self.words(self.CTX + 0x10)[0], self.words(self.CTX + 0x14)[0]

    def pool_string(self, offset: int) -> str | None:
        size, base = self.pool()
        if not base or offset == 0xFFFFFFFF or offset >= size:
            return None
        return self.string(base + offset)

    def ctx(self, index: int, count: int = 1):
        return self.words(self.CTX + index * 4, count)

    def error_flag(self) -> int:
        return self.ctx(7)[0]


# --- command line ---------------------------------------------------------

def _default_image() -> Path:
    return Path(__file__).resolve().parents[4] / "out" / "seg0_c0000000.bin"


def build(image_path=None, survey: bool = False) -> "NbuProbe":
    probe = NbuProbe(load_firmware(image_path or _default_image()))
    probe.install_arena()
    probe.survey = survey
    return probe


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", help="firmware image (default out/seg0_c0000000.bin)")
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index", help="parse the container and list its 221 resource sets")
    index.add_argument("pattern", nargs="?", help="only names matching this substring")
    index.add_argument("--json", help="also write the table to this file")
    load = sub.add_parser("set", help="parse one resource set and trace its records")
    load.add_argument("name")
    load.add_argument("--records", type=int, default=12)
    mp = sub.add_parser("map", help="walk a whole set and tally its records")
    mp.add_argument("name")
    mp.add_argument("--json", help="write the record map to this file")
    args = parser.parse_args(argv)

    probe = build(args.image, survey=True)
    if args.command == "index":
        rows = probe.index()
        shown = [r for r in rows if not args.pattern or args.pattern.lower() in r["name"].lower()]
        for row in shown:
            print(f"{row['hash']:08X}  0x{row['address']:08X}  +0x{row['offset']:07X}  {row['name']}")
        print(f"-- {len(shown)} of {len(rows)} resource sets "
              f"(pool 0x{probe._pool[0]:X} bytes at 0x{probe._pool[1]:08X})")
        if args.json:
            Path(args.json).write_text(json.dumps(
                {"_source": "emulated: FUN_c05e6400 over out/seg0_c0000000.bin, "
                            "tags 1 and 0x10001; see research/ui/tools/nbu_probe/",
                 "nbu_base": "0x%08X" % probe.NBU_BASE,
                 "pool": {"size": probe._pool[0], "base": "0x%08X" % probe._pool[1]},
                 "sets": [{"name": r["name"], "hash": "0x%08X" % r["hash"],
                           "address": "0x%08X" % r["address"],
                           "offset": "0x%X" % r["offset"],
                           "pool_offset": "0x%X" % r["pool_offset"]} for r in rows]},
                indent=1) + "\n")
            print(f"-- wrote {args.json}")
        return 0

    if args.command == "map":
        import collections
        records = probe.map_set(args.name)
        tally = collections.Counter(r["tag"] for r in records)
        row = [r for r in probe.index() if r["name"] == args.name][0]
        last = records[-1]
        print(f"{args.name}: {len(records)} records, "
              f"0x{row['address']:08X}..0x{last['address'] + last['size']:08X}")
        for tag, count in sorted(tally.items()):
            print(f"  tag 0x{tag:08X}  x{count}")
        if args.json:
            Path(args.json).write_text(json.dumps(
                {"_source": "emulated: FUN_c05e6400 record boundaries",
                 "set": args.name, "address": "0x%08X" % row["address"],
                 "records": [{"index": r["index"], "tag": "0x%08X" % r["tag"],
                              "address": "0x%08X" % r["address"],
                              "size": r["size"]} for r in records]},
                indent=1) + "\n")
            print(f"-- wrote {args.json}")
        return 0

    probe.index()
    probe.open_set(args.name)
    for i in range(args.records):
        try:
            trace = probe.record()
        except ProbeError as exc:
            print(f"record {i}: STOPPED -- {exc}")
            return 1
        names = [c.name for c in trace.calls]
        print(f"record {i}  tag 0x{trace.token:08X}  result {trace.result}  "
              f"{trace.consumed} bytes  {len(trace.calls)} calls")
        if names:
            print("           " + ", ".join(dict.fromkeys(names)))
        if trace.strings:
            print("           strings: " + ", ".join(trace.strings[:8]))
        if trace.result:
            break
    if probe.discovered:
        print("-- auto-stubbed (survey mode, each returned 0): "
              + ", ".join(f"0x{a:08X}" for a in sorted(probe.discovered)))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
