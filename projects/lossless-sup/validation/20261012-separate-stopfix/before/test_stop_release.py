"""Stock stop-queue release instructions used by the integrated lossless patch.

Promoted from the 2026-10-11 community review. The built LOSS install/restore
and exclusive claim are covered by test_v3_lossless/test_card_emulation.
Actual queue, parent/child reference and RAW cleanup instructions execute;
locks and allocator/pool-return boundaries are explicit substitutes. No real
DMA, scheduling, concurrent descriptor reuse or camera I/O is tested.
"""
import hashlib
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'fpSup/raw/lossless_codec'))
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell/v3'))
from test_native_writer_contract import StockWriter, STOP, STACK

IMAGE = ROOT / 'out/seg0_c0000000.bin'
IMAGE_SHA = 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
SITE, STOCK, PATCH = 0xC0377118, 0xE92D4030, 0xEA000160
MGR, OBJ, NODE, RAW = 0x45002000, 0x45002400, 0x48000000, 0x49000000
RANGES = [(SITE, 0xC0377150), (0xC03776A0, 0xC0377730),
          (0xC0375030, 0xC0375178), (0xC03753C0, 0xC0375400),
          (0xC03768D8, 0xC0376AF8), (0xC0381008, 0xC0381090),
          (0xC0374180, 0xC03741D0), (0xC03777B8, 0xC03779D8),
          (0xC037B1F0, 0xC037B248), (0xC037D880, 0xC037D898),
          (0xC037E008, 0xC037E060)]
CALLS = [0xC0377688, 0xC03840C0, 0xC03840D8, 0xC03841BC,
         0xC03842E8, 0xC0384300, 0xC038F3F8, 0xC038F410,
         0xC038F51C, 0xC038F524, 0xC0398D34, 0xC0398D3C]


def pinned(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise AssertionError('input hash mismatch: ' + str(path))
    return data


class Flush(StockWriter):
    def __init__(self, patched=True):
        super().__init__(pinned(IMAGE, IMAGE_SHA))
        self.mu.mem_map(NODE, 0x100000)
        self.returned, self.buffers, self.locks = [], [], {}
        self.raw_bytes = {}
        if patched:
            self.put(SITE, PATCH)
        self.substitutes = {
            0xC0019DC0: lambda: self.ret(0x1234),
            0xC001A048: self.ret, 0xC001A288: self.ret,
            0xC0374220: lambda: self.ret(MGR),
            0xC0377348: lambda: self.ret(OBJ),
            0xC037AED8: lambda: self.ret(OBJ + 0x100),
            0xC037D580: lambda: self.ret(OBJ + 0x200),
            0xC037DD08: lambda: self.ret(OBJ + 0x300),
            0xC0010298: self.queue_lock,
            0xC00102D0: self.queue_unlock,
            0xC036DCC8: lambda: self.ret(0),
            0xC00101C0: self.manager_lock,
            0xC0010210: self.manager_unlock,
            0xC001D3D0: self.buffer_free,
            0xC0380580: self.pool_return,
        }
        # Match the maintained v3 harness: also place bx lr at every substituted
        # boundary because a PC write from a Unicorn hook can be ignored.
        for address in self.substitutes:
            self.put(address, 0xE12FFF1E)

    def queue_lock(self):
        token, owner = self.r('r0'), self.r('r1')
        if owner in self.locks:
            raise AssertionError('recursive queue acquisition')
        self.locks[owner] = token
        self.put(token, owner)
        self.ret(token)

    def queue_unlock(self):
        owner = self.get(self.r('r0'))
        if self.locks.pop(owner, None) is None:
            raise AssertionError('unowned queue unlock')
        self.ret()

    def manager_lock(self):
        if self.r('r0') != MGR or MGR in self.locks:
            raise AssertionError('unexpected manager acquisition')
        self.locks[MGR] = 0xCAFE
        self.ret(0xCAFE)

    def manager_unlock(self):
        if (self.r('r0'), self.r('r1')) != (MGR, 0xCAFE):
            raise AssertionError('unexpected manager unlock')
        if self.locks.pop(MGR, None) != 0xCAFE:
            raise AssertionError('unowned manager unlock')
        self.ret()

    def buffer_free(self):
        handle = self.get(self.r('r0'))
        if handle not in self.raw_bytes or handle in self.buffers:
            raise AssertionError('unknown or duplicate RAW buffer release')
        self.buffers.append(handle)
        self.ret()

    def pool_return(self):
        frame = self.r('r0')
        if self.r('r1') != 3 or frame in self.returned:
            raise AssertionError('unknown or duplicate node return')
        if not NODE <= frame < NODE + 96 * 0x2000:
            raise AssertionError('out-of-pool node')
        self.returned.append(frame)
        self.ret()

    def node(self, slot, parent=0xFFFFFFFF, refs=0, raw_refs=0, raw_slot=None):
        frame = NODE + slot * 0x2000
        self.put(MGR + 4 + slot * 4, frame)
        self.put(MGR + 0x18C, self.get(MGR + 0x18C) + 1)
        for off, value in [(4, 1), (0x10FC, slot), (0x1118, parent),
                           (0x1110, refs), (0x1114, raw_refs)]:
            self.put(frame + off, value)
        if raw_slot is None:
            raw_slot = slot
        handle = RAW + raw_slot * 0x2000
        self.raw_bytes[handle] = 1441792
        self.put(frame + 0x68, handle)
        self.put(frame + 0x6C, 1441792)
        self.put(frame + 0x70, 10)
        # All other native buffer wrappers are absent (allocator type 15).
        for off in list(range(0x74, 0x128, 12)) + [0x12C, 0x18C, 0xFD0, 0xFDC, 0xFE8]:
            self.put(frame + off + 8, 15)
        return frame

    def queue(self, frames):
        self.put(OBJ + 0x14, frames[0] if frames else 0)
        self.put(OBJ + 0x18, frames[-1] if frames else 0)
        for i, frame in enumerate(frames):
            self.put(frame + 0x110C, frames[i + 1] if i + 1 < len(frames) else 0)

    def invoke(self, addr=SITE, **registers):
        self.allowed, self.stops, self.stubs = RANGES, {STOP}, self.substitutes
        self.reached = None
        self.setr('sp', STACK - 0x100)
        self.setr('lr', STOP)
        for name, value in registers.items():
            self.setr(name, value)
        self.mu.emu_start(addr, 0, count=200000)
        if self.reached != STOP:
            raise AssertionError('did not return within instruction budget')
        if self.r('sp') != STACK - 0x100 or self.locks:
            raise AssertionError('stack or lock not restored')


class StopReleaseTests(unittest.TestCase):
    def test_branch_and_all_twelve_direct_call_sites(self):
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
        image = pinned(IMAGE, IMAGE_SHA)
        md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        ins = list(md.disasm(struct.pack('<I', PATCH), SITE))[0]
        self.assertEqual((ins.mnemonic, ins.op_str), ('b', '#0xc03776a0'))
        actual = []
        for off in range(0, len(image) - 4, 4):
            w = struct.unpack_from('<I', image, off)[0]
            if w >> 24 != 0xEB:
                continue
            imm = w & 0xFFFFFF
            if imm & 0x800000:
                imm -= 0x1000000
            if 0xC0000000 + off + 8 + imm * 4 == SITE:
                actual.append(0xC0000000 + off)
        self.assertEqual(actual, CALLS)
        getters = {0xC037AED8, 0xC037D580, 0xC037DD08, 0xC0374220}
        for a in actual:
            following = list(md.disasm(image[a + 4 - 0xC0000000:a + 12 - 0xC0000000], a + 4))
            first = following[0]
            if first.mnemonic == 'bl':
                self.assertIn(int(first.op_str[1:], 16), getters)
            else:
                self.assertEqual([(i.mnemonic, i.op_str) for i in following],
                                 [('mov', 'r1, #1'), ('mov', 'r0, r1')])

    def test_stock_drops_44_but_patch_releases_44(self):
        for patched in (False, True):
            r = Flush(patched)
            frames = [r.node(i) for i in range(44)]
            r.queue(frames)
            r.invoke(r0=OBJ)
            self.assertEqual((r.get(OBJ + 0x14), r.get(OBJ + 0x18)), (0, 0))
            self.assertEqual(len(r.returned), 44 if patched else 0)
            self.assertEqual(len(r.buffers), 44 if patched else 0)
            self.assertEqual(r.get(MGR + 0x18C), 0 if patched else 44)
            for i in range(44):
                self.assertEqual(r.get(MGR + 4 + i * 4), 0 if patched else frames[i])

    def test_parent_survives_until_active_child_completes(self):
        r = Flush()
        parent = r.node(0, refs=2, raw_refs=2)
        queued = r.node(1, parent=0, raw_slot=0)
        active = r.node(2, parent=0, raw_slot=0)
        r.queue([queued])
        r.invoke(r0=OBJ)
        self.assertEqual(r.returned, [queued])
        self.assertEqual(r.buffers, [])
        self.assertEqual((r.get(parent + 0x1110), r.get(parent + 0x1114)), (1, 1))
        self.assertEqual(r.get(MGR + 4), parent)
        r.invoke(0xC0375030, r0=MGR, r1=2)
        self.assertEqual(r.returned, [queued, active, parent])
        self.assertEqual(len(r.buffers), 1)
        self.assertEqual(r.get(MGR + 0x18C), 0)

    def test_sequential_duplicate_release_is_noop(self):
        r = Flush()
        parent = r.node(0, refs=1, raw_refs=1)
        child = r.node(1, parent=0, raw_slot=0)
        r.queue([child])
        r.invoke(r0=OBJ)
        r.invoke(0xC0375030, r0=MGR, r1=1)
        r.invoke(0xC0375030, r0=MGR, r1=0)
        self.assertEqual(r.returned, [child, parent])
        self.assertEqual(len(r.buffers), 1)
        self.assertEqual(r.get(parent + 0x1110), 0)

    def test_empty_queue_preserves_callee_registers(self):
        r = Flush()
        regs = {f'r{i}': 0x11220000 + i for i in range(4, 12)}
        r.queue([])
        r.invoke(r0=OBJ, **regs)
        self.assertEqual({n: r.r(n) for n in regs}, regs)
        self.assertEqual(r.returned, [])

    def test_busy_manager_does_not_release(self):
        r = Flush()
        frame = r.node(0)
        r.mu.mem_write(MGR + 0x190, b'\x01')
        r.queue([frame])
        r.invoke(r0=OBJ)
        self.assertEqual(r.returned, [])
        self.assertEqual(r.get(MGR + 4), frame)
        # A busy manager still loses the popped queue; patch is not a busy-flag fix.
        self.assertEqual(r.get(OBJ + 0x14), 0)

    def test_parent_decrement_mutation_is_detected(self):
        r = Flush()
        parent = r.node(0, refs=1, raw_refs=1)
        child = r.node(1, parent=0, raw_slot=0)
        r.put(0xC0375100, 0xE1A02002)  # private mov r2,r2 instead of sub r2,r2,#1
        r.queue([child])
        r.invoke(r0=OBJ)
        with self.assertRaises(AssertionError):
            self.assertEqual(r.get(MGR + 4), 0)
        self.assertEqual(r.get(MGR + 4), parent)


if __name__ == '__main__':
    unittest.main()
