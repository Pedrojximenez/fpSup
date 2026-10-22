"""Execute stock ARM queue, writer gate and SSD scatter helpers offline.

Only the named ROM ranges execute; log, IRQ and object lookup boundaries are
explicit fixtures. No scheduler, DMA, cache or actual filesystem is simulated.
This checks the decompiled control-flow interpretation, not camera timing.
"""
from pathlib import Path
import hashlib
import json
import struct
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as R

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ROM = ROOT/'out/MAIN_c0000000.bin'
STACK, STOP, OBJECT, FRAME, VT = 0x10000000, 0x10100000, 0xc3e00000, 0xc3e10000, 0xc3e20000


class Native:
    def __init__(self, ranges, stubs=None):
        self.image = ROM.read_bytes()
        self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.mu.mem_map(0xc0000000, 0x04400000)
        self.mu.mem_write(0xc0000000, self.image)
        self.mu.mem_map(STACK, 0x10000)
        self.mu.mem_map(STOP, 0x1000)
        self.ranges, self.stubs = ranges, stubs or {}
        self.reached_stop = False
        self.calls = []
        self.native_stack_mod8 = []
        self.mu.hook_add(UC_HOOK_CODE, self.code)

    def w(self, p):
        return struct.unpack('<I', self.mu.mem_read(p, 4))[0]

    def put(self, p, v):
        self.mu.mem_write(p, struct.pack('<I', v & 0xffffffff))

    def code(self, mu, p, size, _):
        if p == STOP:
            self.reached_stop = True
            mu.emu_stop()
            return
        if p in self.stubs:
            args = [mu.reg_read(getattr(R, 'UC_ARM_REG_R'+str(i))) for i in range(4)]
            self.calls.append((hex(p), args))
            # These are untouched native bodies, some of which use the
            # firmware's four-byte internal stack convention. Record it;
            # do not impose our new-hook AAPCS rule on the original ROM.
            self.native_stack_mod8.append((hex(p), mu.reg_read(R.UC_ARM_REG_SP) % 8))
            value = self.stubs[p](self, args)
            lr = mu.reg_read(R.UC_ARM_REG_LR)
            for i in (0, 1, 2, 3, 12):
                mu.reg_write(getattr(R, 'UC_ARM_REG_R'+str(i)), 0xbad00000+i)
            mu.reg_write(R.UC_ARM_REG_R0, 0 if value is None else value)
            mu.reg_write(R.UC_ARM_REG_PC, lr)
            return
        assert any(a <= p < b for a, b in self.ranges), f'unmodeled ROM {p:#x}'

    def call(self, p, *args, thumb=False):
        seeds = [0x76540000+i for i in range(8)]
        for i, value in enumerate(seeds, 4):
            self.mu.reg_write(getattr(R, 'UC_ARM_REG_R'+str(i)), value)
        for i, value in enumerate(args):
            self.mu.reg_write(getattr(R, 'UC_ARM_REG_R'+str(i)), value & 0xffffffff)
        self.mu.reg_write(R.UC_ARM_REG_SP, STACK+0xfff0)
        self.mu.reg_write(R.UC_ARM_REG_LR, STOP)
        self.reached_stop = False
        self.mu.emu_start(p | int(thumb), STOP+4, count=20000)
        assert self.reached_stop, f'no native return at {p:#x}'
        assert self.mu.reg_read(R.UC_ARM_REG_SP) == STACK+0xfff0
        assert [self.mu.reg_read(getattr(R, 'UC_ARM_REG_R'+str(i))) for i in range(4,12)] == seeds
        return self.mu.reg_read(R.UC_ARM_REG_R0)


class Contracts(unittest.TestCase):
    def test_native_fifo_keeps_event8_and9_behind_earlier_headers(self):
        cam = Native([(0xc00045b8, 0xc0004750)], {
            0xc000ec14: lambda c,a: 0xc0,  # IRQ-masked fixture avoids scheduling.
            0xc000ec24: lambda c,a: 0,
        })
        queue = 7
        control = 0xc30139b4 + queue*0x24
        for attr in (1, 3):
            cam.put(control, control)  # empty waiting-task list
            cam.put(control+8, 1)     # allocated native mailbox
            cam.put(control+0x10, attr)
            cam.put(control+0x14, 0)
            cam.put(control+0x18, 0)
            addresses = [OBJECT+i*0x200 for i in range(5)]
            events = [5, 5, 5, 8, 9]
            for p, event in zip(addresses, events):
                cam.put(p, 0xdeadbeef)
                cam.put(p+4, 0x2b)  # native message kind / priority key
                cam.put(p+0xc, event)
                self.assertEqual(cam.call(0xc00045b8, queue, p), 0)
            got, p = [], cam.w(control+0x14)
            while p:
                self.assertLess(len(got), len(events))
                got.append(cam.w(p+0xc))
                p = cam.w(p)
            self.assertEqual(got, events)
        # Even a priority mailbox compares kind +4, not subevent +C. All
        # these native kind2B messages are equal; no proposed patch is tested.

    def test_event8_advance_is_required_to_queue_next_writer(self):
        held, submitted = [], []

        def lookup(c, a):
            self.assertEqual(a[1], 83)
            return FRAME

        def append(c, a):
            self.assertEqual(a[:2], [OBJECT+0x10, FRAME])
            held.append(FRAME)
            c.put(OBJECT+0x14, held[0])
            return 1

        def pop(c, a):
            self.assertEqual(a[0], OBJECT+0x10)
            value = held.pop(0)
            c.put(OBJECT+0x14, held[0] if held else 0)
            return value

        def submit(c, a):
            self.assertEqual(a[0], OBJECT)
            # C037DD50 hands its stack-local native request to C0377008.
            submitted.append(c.w(a[1]+4))
            return 1

        cam = Native([(0xc037dd50, 0xc037dee0), (0xc0376f20, 0xc0376f88),
                      (0xc037df40, 0xc037e008)], {
            0xc0019dc0: lambda c,a: 0,
            0xc001a048: lambda c,a: 0,
            0xc0374220: lambda c,a: 0xc351ff44,
            0xc03753c0: lookup,
            0xc0381090: append,
            0xc0381008: pop,
            0xc0377008: submit,
        })
        cam.put(OBJECT, VT)
        cam.put(VT+0x10, 0xc037dd50)
        cam.put(VT+0x14, 0xc0376f20)
        cam.put(OBJECT+0x1c, 82)  # writer currently owns previous frame
        cam.put(FRAME+4, 1)
        cam.put(FRAME+0x10fc, 83)
        cam.mu.mem_write(FRAME, b'\x01')
        self.assertEqual(cam.call(0xc037dd50, OBJECT, 83, 1), 1)
        self.assertEqual(held, [FRAME])
        self.assertEqual(submitted, [])
        self.assertEqual(cam.w(OBJECT+0x1c), 82)
        # The event8 branch in C038C058 uses this exact native call.
        self.assertEqual(cam.call(0xc037df40, OBJECT, 0xffffffff), 1)
        self.assertEqual(held, [])
        self.assertEqual(submitted, [83])
        self.assertEqual(cam.w(OBJECT+0x1c), 83)

    def test_ssd_bulk_retains_addresses_and_splits_at_64k(self):
        cam = Native([(0xc0670248, 0xc06703d8), (0xc0670420, 0xc0670450),
                      (0xc0670690, 0xc0670768)], {
            0xc000ec14: lambda c,a: 0xc0,
            0xc000ec24: lambda c,a: 0,
        })
        source, length = 0x53b00c00, 1095168
        token = cam.call(0xc06702b8, thumb=True)
        self.assertEqual(token, 0x442f77d8)
        self.assertEqual(cam.call(0xc0670338, source, length, thumb=True), 0)
        self.assertEqual(cam.w(0xc42f97d8), 1)
        self.assertEqual(cam.w(0xc42f77d8), source-0x40000000)
        self.assertEqual(cam.w(0xc42f77dc), length)
        self.assertEqual(cam.w(0xc42f97e0), length)
        # The native 'copy' operation stores a scatter segment, not its bytes.
        cam.put(OBJECT, token)
        cam.put(OBJECT+4, length)
        got = []
        while cam.w(OBJECT+4):
            cam.call(0xc0670690, OBJECT, thumb=True)
            got.append((cam.w(OBJECT+8), cam.w(OBJECT+12)))
        self.assertEqual(len(got), 17)
        offset = 0
        for address, n in got:
            self.assertEqual(address, source-0x40000000+offset)
            self.assertEqual(n, min(65536, length-offset))
            offset += n
        self.assertEqual(offset, length)
        self.assertEqual(cam.w(0xc42f9800), length)
        # No dropped, reordered or inserted prefix in this seeded helper path.
        # This does not test TRBs, actual DMA, source header placement or media.


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    folder = HERE/'recycle-source-audit'
    folder.mkdir(exist_ok=True)
    (folder/'native-arm-contract.json').write_text(json.dumps({
        'firmware': str(ROM), 'sha256': hashlib.sha256(ROM.read_bytes()).hexdigest(),
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'passed': result.wasSuccessful(), 'camera_changed': False,
        'limits': 'Stock functions with explicit object/IRQ/log boundaries; no scheduler, cache, DMA or storage timing.'
    }, indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
