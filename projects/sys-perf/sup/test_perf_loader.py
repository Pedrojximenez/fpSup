#!/usr/bin/env python3
"""70PERF.BIN through the real Loader v3 (LOADER.BIN + loader.S) in unicorn,
using fpSup/fp_usb_shell/v3/test_v3.py's Camera: claims, install, the
power-off write-back, a warm restart's leftovers, and a conflicting sup.

Covers every write type: data words, ARM bl (dirtyclean, lz4fast,
inputredraw), Thumb blx to an ARM veneer (pagelru, C05DD5CA is only
2-aligned and claimed as C05DD5C8..CF) and Thumb b.w to a Thumb veneer
(iconcache).

    python3 -B -m unittest test_perf_loader      (from projects/sys-perf/sup)
"""
import pathlib, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'))
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
sys.path.insert(0, str(HERE))
import test_v3 as T                       # noqa: E402
import build_perf as P                         # noqa: E402

BLV3 = 0xE51FF004          # ARM veneer: ldr pc, [pc, #-4]
TV3 = 0xF000F8DF           # Thumb veneer: ldr.w pc, [pc, #0]


def bl_to(at, insn):
    off = insn & 0xFFFFFF
    if off & 0x800000:
        off -= 1 << 24
    return at + 8 + 4 * off


def thumb_to(at, h1, h2):
    """Target of a Thumb bl/blx/b.w (T1/T2/T4) at `at`; (target, kind)."""
    S = (h1 >> 10) & 1
    i1 = 1 - (((h2 >> 13) & 1) ^ S)
    i2 = 1 - (((h2 >> 11) & 1) ^ S)
    imm = (S << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if S:
        imm -= 1 << 25
    if h2 & 0xD000 == 0xC000:                      # blx: Align(PC, 4)
        return ((at + 4) & ~3) + imm, 'blx'
    if h2 & 0xD000 == 0x9000:
        return at + 4 + imm, 'b.w'
    return at + 4 + imm, 'bl'


import os
WITHOUT = {x for x in os.environ.get('PERF_WITHOUT', '').split(',') if x}   # e.g. ic,pl = the lean build


class PerfThroughLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.info, cls.sym = P.build(set(), 1, without=WITHOUT)
        cls.has = {k: k not in WITHOUT for k in P.OPTIONAL}
        cls.claims = [(int(c['addr'], 16), [int(x, 16) for x in c['stock'].split()])
                      for c in cls.info['claims']]
        cls.writes = cls.info['writes']

    def boot(self, *extra, stale=None, name='70PERF.BIN'):
        cam = T.Camera(*T.card(*extra, (name, self.blob)), stale=stale)
        r0, sp = cam.boot()
        self.assertEqual(cam.misaligned, [])
        return cam

    def block(self, cam):
        st = cam.state()
        for i in range(T.MAX_SUPS):
            b = cam.w(st + T.O_SUPS + T.SUP_BYTES * i + 44)
            if b and cam.w(b + 32) == 0x46524550:
                return b
        return None

    def h(self, cam, a):
        return struct.unpack('<H', bytes(cam.mu.mem_read(a, 2)))[0]

    def assert_stock(self, cam):
        for a, ws in self.claims:
            for i, s in enumerate(ws):
                self.assertEqual(cam.w(a + 4 * i), s, f'{a + 4 * i:#x}')

    def test_installs_every_word(self):
        cam = self.boot()
        log = cam.log()
        self.assertIn('70PERF.BIN', [t for c, _, _, t in log if c == 'LOADED'])
        blk = self.block(cam)
        self.assertIsNotNone(blk)
        body = blk + 32
        self.assertEqual(cam.w(body + 0x14), 1, 'pf_state')
        self.assertEqual(cam.w(body + 0x04), 4, 'layout version')
        ven = cam.w(body + 0x18)
        self.assertTrue(T.cave.CAVE_ARENA <= ven < 0xC072EFB4, hex(ven))
        k = 0
        kinds = set()
        for w in self.writes:
            a = int(w['addr'], 16)
            target = body + self.sym[w['target']]
            kinds.add(w['type'])
            if w['type'] == 'data':
                self.assertEqual(cam.w(a), target, f'{a:#x}')
                continue
            v = ven + 8 * k
            k += 1
            if w['type'] == 'bl':
                self.assertEqual(bl_to(a, cam.w(a)), v, f'{a:#x} bl')
                self.assertEqual((cam.w(v), cam.w(v + 4)), (BLV3, target))
            else:
                t, kind = thumb_to(a, self.h(cam, a), self.h(cam, a + 2))
                want = 'blx' if w['type'] == 'thumb-blx' else 'b.w'
                self.assertEqual((t, kind), (v, want), f'{a:#x} {w["type"]}')
                self.assertEqual((cam.w(v), cam.w(v + 4)), (BLV3 if want == 'blx' else TV3, target))
        want_kinds = {'data', 'bl'} | ({'thumb-blx'} if self.has['pl'] else set()) \
            | ({'thumb-b.w'} if self.has['ic'] else set())
        self.assertEqual(kinds, want_kinds)
        self.assertEqual(k, self.info['veneers'])
        if self.has['pl']:
            # the 2-aligned pagelru site: the other halfwords of C05DD5C8..CF untouched
            st = dict(self.claims)[0xC05DD5C8]
            self.assertEqual(self.h(cam, 0xC05DD5C8), st[0] & 0xFFFF)
            self.assertEqual(self.h(cam, 0xC05DD5CE), st[1] >> 16)
        # a left-out module: no claim, no write, offset word 0
        claimed = {a for a, _ in self.claims}
        for k_, sites in (('pl', (0xC05DD5C8, 0xC05DD670)), ('ic', (0xC060219C, 0xC060234C)),
                          ('ir', (0xC06D1418,)), ('al', (0xC0561734,)), ('wf', P.WF_SLOTS)):
            for a in sites:
                self.assertEqual(any(c <= a < c + 8 for c in claimed), self.has[k_], f'{k_} {a:#x} claimed?')
        # module init done by the entry: every switch 0, iconcache arena = block BSS
        dc = body + self.sym['dc_mod']
        self.assertEqual((cam.w(dc + 4), cam.w(dc + 8), cam.w(dc + 12)), (0, 0, 0xF))
        self.assertEqual(cam.w(body + self.sym['fd_mod'] + 8), 0)
        offs = {0x54: 'ir', 0x58: 'ic', 0x5C: 'pl', 0x40: 'al', 0x44: 'wf'}
        for off, k_ in offs.items():
            self.assertEqual(cam.w(body + off), self.sym[f'{k_}_mod'] if self.has[k_] else 0, f'+{off:#x} {k_}')
        if self.has['ir']:
            self.assertEqual(cam.w(body + self.sym['ir_mod'] + 8), 0, 'ir_enable')
        if self.has['pl']:
            self.assertEqual(cam.w(body + self.sym['pl_mod'] + 4), 0, 'pagelru enable')
        if self.has['al']:
            self.assertEqual(cam.w(body + self.sym['al_mod'] + 8), 0, 'alphalut enable (module ships 1)')
            self.assertEqual(cam.w(body + self.sym['al_mod']), 0x54554C41, "alphalut 'ALUT'")
        if self.has['wf']:
            self.assertEqual(cam.w(body + self.sym['wf_mod'] + 4), 0, 'waveform enable (module ships 1)')
            self.assertEqual(cam.w(body + self.sym['wf_mod']), 0x45564157, "waveform 'WAVE'")
        arena = (body + self.sym['pf_end'] + 7) & ~7
        if self.has['ic']:
            ic = body + self.sym['ic_mod']
            self.assertEqual((cam.w(ic + 4), cam.w(ic + 8), cam.w(ic + 12)), (0, arena, P.IC_ARENA))
            self.assertLessEqual(arena + P.IC_ARENA, blk + self.info['block_size'])
        else:
            self.assertEqual(self.info['ic_arena'], 0)
            self.assertLess(self.info['block_size'], 0x10000, 'lean block carries no arena')
        # every word journaled with the declared stock bytes
        j = {a: d for a, n, d in cam.journal()}
        for a, ws in self.claims:
            self.assertEqual(j.get(a), b''.join(struct.pack('<I', s) for s in ws), f'{a:#x} journal')
        self.assertIn('PERF ctl', ' '.join(t for *_, t in log) + self._log_text(cam))

    def _log_text(self, cam):
        return ''.join(cam.written.get('\\fpSup\\LOAD.LOG', b'').decode('latin1').split('\0'))

    def test_power_off_puts_every_word_back(self):
        cam = self.boot()
        cam.power_off()
        self.assert_stock(cam)

    def test_warm_restart_leftovers_are_repaired(self):
        stale = {a: 0x45F00001 for a, _ in self.claims[:3]}           # last boot's heap
        stale.update({a: 0xEB0DEAD0 for a, _ in self.claims[-6:]})    # stale branches, Thumb ones too
        cam = self.boot(stale=stale)
        rep = [x[1] for x in cam.log() if x[0] == 'REPAIRED']
        self.assertEqual(sorted(rep), sorted(stale))
        cam.power_off()
        self.assert_stock(cam)

    def test_conflict_releases_and_writes_nothing(self):
        victims = (self.claims[0][0], self.claims[-1][0]) + ((0xC05DD5C8,) if self.has['pl'] else ())
        for victim in victims:
            stock = dict(self.claims)[victim][0]
            other = T.test_sup('TSTX', [(victim, stock, 2, 0xE1A00000)])
            cam = self.boot(('10OTHER.BIN', other))
            log = cam.log()
            self.assertIn('70PERF.BIN', [t for c, _, _, t in log if c == 'RELEASED'], hex(victim))
            for a, ws in self.claims:
                for i, s in enumerate(ws):
                    if a + 4 * i != victim:
                        self.assertEqual(cam.w(a + 4 * i), s, f'{a + 4 * i:#x} written although released')
            self.assertEqual(cam.w(victim), 0xE1A00000)

    def test_chain_holder_on_a_branch_site_also_blocks(self):
        for typ in ('bl', 'thumb-b.w') if self.has['ic'] else ('bl',):
            a = next(int(w['addr'], 16) for w in self.writes if w['type'] == typ)
            stock = dict(self.claims)[a][0]
            other = T.test_sup('TSTC', [(a, stock, 1, 0)])            # CHAIN claim, no write
            cam = self.boot(('10OTHER.BIN', other))
            self.assertIn('70PERF.BIN', [t for c, _, _, t in cam.log() if c == 'RELEASED'], typ)


if __name__ == '__main__':
    unittest.main()
