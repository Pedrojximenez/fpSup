#!/usr/bin/env python3
"""Every sensor merge on one scene (RULES §34-35): from mode 10, batch-write a target readout, set HMAX / receiver,
grab two consecutive frames, reset (poff + AF).  The registers are the mode-table difference mode 10 -> target
(research/imx410/analysis/imx410_modes.csv) or a hand set; every variant also gets 005D=05 (+129 DN12 black) so
binned darks are not clipped.

    bins.py OUT [NAME ...]        default: all variants, skipping those already captured
"""
import csv, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402
import l7                                                             # noqa: E402

A = HERE.parents[1] / 'research' / 'imx410' / 'analysis' / 'imx410_modes.csv'
MODES = {r['mode_id']: r for r in csv.DictReader(open(A))}


def diff(to, frm='10'):
    a, b = MODES[frm], MODES[to]
    return [(int(k[6:], 16), int(b[k])) for k in b if k.startswith('reg_') and a[k] != b[k]]


L4 = [(0x0016, 0x32), (0x001C, 0x02), (0x0058, 0x70), (0x0717, 0x06), (0x071E, 0x03), (0x0722, 0x02), (0x0723, 0x02),
      (0x0724, 0x04), (0x0725, 0x04), (0x0728, 0x3F), (0x072A, 0xA0), (0x072B, 0x02), (0x072C, 0x06), (0x0734, 0x03),
      (0x0737, 0x02), (0x0738, 0x02), (0x0739, 0x04), (0x073A, 0x04), (0x0792, 0x30), (0x0793, 0x03), (0x079C, 0x3D),
      (0x0242, 0x2C), (0x0278, 0x04), (0x0279, 0x01), (0x027B, 0x04), (0x08B6, 0x01), (0x08B7, 0x68), (0x0003, 0x00),
      (0x0018, 0x12)]
FAM14 = [(r, v) for r, v in json.loads((HERE / 'captures' / 'l7' / 'fam14.json').read_text()) if r != 0x0001]
DARK = [(0x0018, 0x12)]
LATCH = False

# name: (regs, HMAX, receiver END/12 or None, yend (0 = keep), 14-bit receive)
V = {
    'm10_1x1':     ([], 445, None, 0, False),
    'm98_2x2':     (diff('98') + DARK, 445, 0xFC, 1500, False),
    'm58_2x2fast': (diff('58') + DARK, 330, 0xFC, 1500, False),
    'vbin2':       (l7.VBIN2 + [(0x0001, 0x2A)], 445, None, 1500, False),
    'vbin2_14':    (FAM14 + l7.VBIN2 + [(0x0001, 0x29)], 911, None, 1500, True),
    'h2_3B':       ([(0x0001, 0x3B)], 445, 0xFC, 0, False),
    'm139_3x3':    (diff('139') + DARK, 445, 0xA8, 1000, False),
    'm8_3x3fast':  (diff('8') + DARK, 330, 0xA8, 1000, False),
    'vbin3':       (L4 + [(0x0001, 0x2A)], 445, None, 1000, False),
    'm140_3x6':    (diff('140') + DARK, 445, 0xA8, 500, False),
}
V['m10_end'] = V['m10_1x1']
BASEMODE = {}
SOC = {}
NOBLACK = set()
POST = {}
READOUT = {}                                            # name -> (R10 readout value, x0, x1, y0, y1): call the firmware's SoC readout setup                                               # BUFA writes after the re-window, BUFA stopped                                                # extra SoC receiver writes after the batch
FAST_SOC = [(0x30100054, 0x350), (0x30100060, 0x01000A02), (0x3010008C, 0x015E0000)]   # mode 8 values (10: 0x51, 0x1000002, 0x2210000)
V['m58_soc'] = V['m58_2x2fast']; SOC['m58_soc'] = FAST_SOC
V['m8_soc'] = V['m8_3x3fast']; SOC['m8_soc'] = FAST_SOC
CRCT8 = [tuple(x) for x in json.loads((HERE / 'captures' / 'crct_m8_values.json').read_text())]   # mode-8 CRCT geometry
V['m8_crct'] = V['m8_3x3fast']; SOC['m8_crct'] = FAST_SOC + CRCT8
V['m8_allsoc'] = V['m8_3x3fast']; SOC['m8_allsoc'] = FAST_SOC + CRCT8 + [(0x30100020, 0x0E370000)]
V['m8_3020'] = V['m8_3x3fast']; SOC['m8_3020'] = FAST_SOC + CRCT8 + [(0x30200054, 0x07BE03DD)]
for _n, _w in (('m8_b228', [(0x30180228, 0x30000101)]), ('m8_b328', [(0x30180328, 0x103)]), ('m8_b3e4', [(0x301803E4, 0x5)]),
               ('m8_b3', [(0x30180228, 0x30000101), (0x30180328, 0x103), (0x301803E4, 0x5)])):
    V[_n] = V['m8_3x3fast']; SOC[_n] = FAST_SOC + CRCT8; POST[_n] = _w
V['m8_rx200'] = V['m8_3x3fast']; SOC['m8_rx200'] = FAST_SOC + CRCT8 + [(0x30100120, 0x350), (0x30100200, 0x01030001)]
for _h in (445, 400, 380, 360, 330):
    V[f'n139_h{_h}'] = (V['m139_3x3'][0], _h, 0xA8, 1000, False); SOC[f'n139_h{_h}'] = FAST_SOC + CRCT8
_BUS = json.loads((HERE / 'captures' / 'magnify' / 'ok1' / 'bus.json').read_text())[4102:4267]   # firmware's 10 -> 8 switch
REPLICA8 = [(int(e['reg'], 16), int(e['val'], 16)) for e in _BUS if e['reg'] != '0x0011']
V['rep8'] = (REPLICA8, 330, 0xA8, 1000, False); SOC['rep8'] = FAST_SOC + CRCT8 + [(0x30100020, 0x0E370000)]; NOBLACK = {'rep8'}
SHADOW8 = [(0x30210028, 0x110700), (0x3021004C, 0x1), (0x302100AC, 0x110000), (0x3021011C, 0x111101)]
V['rep8_sh'] = V['rep8']; SOC['rep8_sh'] = SOC['rep8'] + SHADOW8; NOBLACK.add('rep8_sh')
V['m8_ro'] = V['m8_3x3fast']; SOC['m8_ro'] = FAST_SOC; READOUT['m8_ro'] = (5, 6, 2022, 14, 1014)
V['rep8_ro'] = V['rep8']; SOC['rep8_ro'] = FAST_SOC + [(0x30100020, 0x0E370000)]; READOUT['rep8_ro'] = (5, 6, 2022, 14, 1014); NOBLACK.add('rep8_ro')
V['m8_nodark'] = ([(r, v) for r, v in V['m8_3x3fast'][0] if r != 0x0018], 330, 0xA8, 1000, False); SOC['m8_nodark'] = FAST_SOC + CRCT8
V['n8_dark'] = (DARK, 330, None, 1000, False); BASEMODE['n8_dark'] = 8
V['n8_plain'] = ([], 330, None, 1000, False); BASEMODE['n8_plain'] = 8
CRCT10 = [tuple(x) for x in json.loads((HERE / 'captures' / 'crct_m10_values.json').read_text())]
SLOW_SOC = [(0x30100054, 0x51), (0x30100060, 0x01000002), (0x3010008C, 0x02210000)]
for _n, _soc in (('n8_rx10', SLOW_SOC), ('n8_crct10', CRCT10), ('n8_vmax10', [(0x30100020, 0x0A8B0000)])):
    V[_n] = ([], 330, None, 1000, False); BASEMODE[_n] = 8; SOC[_n] = _soc
for _h in (445, 400, 370, 350, 340):
    V[f'm8_h{_h}'] = (V['m8_3x3fast'][0], _h, 0xA8, 1000, False); SOC[f'm8_h{_h}'] = FAST_SOC                                           # variants that start from another live mode
V['f58_from8'] = (diff('58', '8') + DARK, 330, 0xFC, 1300, False); BASEMODE['f58_from8'] = 8
V['n139_from8'] = (diff('139', '8') + DARK, 445, 0xA8, 1000, False); BASEMODE['n139_from8'] = 8
V['m8f_D1'] = (V['m8_3x3fast'][0] + [(0x00D1, 0xFA)], 330, 0xA8, 1000, False)
V['m58f_D1'] = (V['m58_2x2fast'][0] + [(0x00D1, 0xFA)], 330, 0xFC, 1500, False)
SET = {0x0242, 0x0278, 0x0279, 0x027B, 0x08B6, 0x08B7}                 # MODE21 "no horizontal merge" set
L4_NOSET = [(r, v) for r, v in L4 if r not in SET]
V['v2_noset'] = ([(r, v) for r, v in l7.VBIN2 if r not in SET] + [(0x0001, 0x2A)], 445, None, 1500, False)
V['v3_fix'] = (L4 + [(0x0001, 0x2A), (0x0734, 0x05), (0x0737, 0x00)], 445, None, 1000, False)
V['v3_noset'] = (L4_NOSET + [(0x0001, 0x2A)], 445, None, 1000, False)
V['v3_14'] = (FAM14 + L4_NOSET + [(0x0001, 0x29)], 911, None, 1000, True)   # 14-bit ADC + vertical 3:1 (10-22)
V['v3_noset_fix'] = (L4_NOSET + [(0x0001, 0x2A), (0x0734, 0x05), (0x0737, 0x00)], 445, None, 1000, False)                            # restore check: must match m10_1x1
ORDER = ['m10_1x1', 'm98_2x2', 'vbin2', 'vbin2_14', 'h2_3B', 'm139_3x3', 'vbin3', 'm140_3x6', 'm10_end',
         'm8_3x3fast', 'm58_2x2fast']


def run(out, name):
    regs, hmax, rx, yend, rx14 = V[name]
    regs = regs if name in NOBLACK else [(r, v) for r, v in regs if r != 0x005D] + [(0x005D, 0x05)]
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    (d / 'regs.json').write_text(json.dumps(dict(regs=[f'{r:04X}={v:02X}' for r, v in regs], hmax=hmax, rx=rx,
                                                 yend=yend, rx14=rx14)))
    F.cached_assemble()
    s = F.Session(out, yend, True, BASEMODE.get(name, 10), min_alloc=24 << 20)
    clean = False
    try:
        B.startstop(100)
        if LATCH == 'pre':                              # stop the sensor, write the table, then restart
            s.write(0x0011, 0x00); time.sleep(0.03)
            n = l7.batch(regs)
            s.write(0x0011, 0x01)
        else:
            n = l7.batch(regs)
        B.wr(0x30100004, (hmax - 1) | (hmax - 1) << 16)
        if LATCH is True:                               # restart the sensor AFTER the SoC line time is set: the
            s.write(0x0011, 0x00); time.sleep(0.03); s.write(0x0011, 0x01)   # sensor locks its timing at restart
        if rx:
            B.wr(0x3010000C, rx)
        for ad, va in SOC.get(name, []):
            B.wr(ad, va)
        if rx14:
            B.wr(0x30100800, 0x00112013); B.wr(0x300E10B4, 3)
        print(f'{name}: {n} regs, HMAX {hmax}, rx {rx}, yend {yend}')
        if name in READOUT:
            import cave, struct as _st
            ro = cave.claim('imxl.readout', 16)
            v, x0, x1, y0, y1 = READOUT[name]
            B.P().put(ro, _st.pack('<IHHHHI', v, x0, x1, y0, y1, 0), 'rdout ')
            B.call(0xC0635ED8 | 1, ro)                  # receiver window + readout-mode globals + CRCT (bank 0)
            B.call(0xC0636048 | 1, ro)                  # the same for the second bank
        time.sleep(0.3)
        l7.rewindow(s, 1 if rx14 else 0)
        if POST.get(name):
            B.startstop(100)
            for ad, va in POST[name]:
                B.wr(ad, va)
            B.startstop(10)
        time.sleep(0.5)
        ok = s.grab(d)
        print(name, 'ok' if ok else 'NO FRAME', flush=True)
        st = {}
        for a0 in (0x30100580, 0x301005C0, 0x30100600, 0x30100640):
            for i, x in enumerate(B.P().mem_get(a0, 16)):
                st[f'0x{a0 + 4 * i:08X}'] = x
        (d / 'rxstatus.json').write_text(json.dumps(st, indent=0))
        if ok and rx14:
            m = json.loads((d / 'frame.json').read_text()); m['bits'] = 14
            (d / 'frame.json').write_text(json.dumps(m, indent=1))
        s.write(0x0018, 0x00); s.write(0x005D, 0x03)      # the only written registers outside the mode table
        clean = ok
    except BaseException:
        clean = False
        raise
    finally:
        s.close()                                       # back to mode 8: the firmware rewrites the whole table
        if not clean:
            import sweep
            sweep.KEEP = None
            sweep.fastreboot()


if __name__ == '__main__':
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    if '--latch' in sys.argv:
        sys.argv.remove('--latch'); LATCH = True
    if '--prelatch' in sys.argv:
        sys.argv.remove('--prelatch'); LATCH = 'pre'
    for name in sys.argv[2:] or ORDER:
        if (out / name / 'frame2.raw').exists():
            continue
        if (out / 'STOP').exists():
            break
        run(out, name)
