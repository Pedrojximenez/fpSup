#!/usr/bin/env python3
"""Extract Z CAM E2-F6 (fw 1.0.13) IMX410 driver tables from imvt_camera (static, read-only).

    python3 -I zcam_extract.py <path/to/imvt_camera> [outdir]

Tables (VAs from nm -D / decompile, research notes: zcam_e2f6/notes/ZCAM_E2F6_FIRMWARE.md):
  g_sensor_spec -> 0x132C698  sensor spec: +0x38 count, +0x40 AE register list {bus,?,addr,flags,u64 name}
  0x132C278  readout info  33 x 0x20  {w, h, out_bits, adc_bits, u64 0, char* name}
  0x132CA20  mode table    59 x 0x28  {readout, inck, hmax(InckPerHs), inck_per_vs, vmax, fps, f32 ratio, pad, char* name}  (vmax/inck_per_vs fields unused at runtime)
  0x132D358  s_sensor_register_init_tbl 166 x 70 B {u16 addr, u16 delay_ms, u16 val[33 readouts]}; 0xFFFF = not written
Init order (sensor_init @0xB94990): table rows in order (usleep(delay) after a row) -> AE regs (sensor_n3a_register_init).
"""
import csv, json, os, struct, sys


class Elf:
    def __init__(s, p):
        s.b = open(p, 'rb').read()
        phoff, = struct.unpack_from('<Q', s.b, 0x20)
        n, = struct.unpack_from('<H', s.b, 0x38)
        s.seg = []
        for i in range(n):
            t, fl, off, va, pa, fs, ms, al = struct.unpack_from('<IIQQQQQQ', s.b, phoff + i * 56)
            if t == 1:
                s.seg.append((va, off, fs))

    def rd(s, va, n):
        for va0, o, fs in s.seg:
            if va0 <= va < va0 + fs:
                return s.b[o + va - va0:o + va - va0 + n]
        raise ValueError(hex(va))

    def cstr(s, va):
        b = s.rd(va, 64)
        return b[:b.index(b'\0')].decode('latin1')


def extract(path):
    e = Elf(path)
    spec = struct.unpack('<Q', e.rd(0x132C250, 8))[0]
    assert spec == 0x132C698
    nae = struct.unpack('<I', e.rd(spec + 0x38, 4))[0]
    ae = []
    for i in range(nae):
        bus, x, addr, fl, p = struct.unpack('<IIIIQ', e.rd(spec + 0x40 + i * 24, 24))
        ae.append(dict(idx=i, addr=addr, name=e.cstr(p).strip(), flags=fl))
    ro = []
    for i in range(33):
        w, h, bits, adc, z, p = struct.unpack('<IIIIQQ', e.rd(0x132C278 + i * 0x20, 0x20))
        ro.append(dict(readout=i, name=e.cstr(p).strip(), w=w, h=h, out_bits=bits, adc_bits=adc))
    modes = []
    for i in range(59):
        r, inck, hmax, ipv, vmax, fps, ratio, pad, p = struct.unpack('<IIIIIIfIQ', e.rd(0x132CA20 + i * 0x28, 0x28))
        modes.append(dict(mode=i, name=e.cstr(p), readout=r, sony_mode=ro[r]['name'], hmax=hmax, vmax=vmax,
                          fps_nominal=fps, ratio=round(ratio, 6), inck=inck, inck_per_vs=ipv,
                          # runtime VMAX (FUN_00B93F38): even(round(inck*ratio/fps/hmax)); table vmax is not used for it
                          vmax_runtime=int(inck * ratio / fps / hmax + 0.5) & ~1,
                          fps_runtime=round(inck / hmax / (int(inck * ratio / fps / hmax + 0.5) & ~1), 4)))
    regs = []
    for k in range(166):
        raw = struct.unpack('<35H', e.rd(0x132D358 + k * 70, 70))
        regs.append(dict(order=k, addr=raw[0], delay_ms=raw[1], val=list(raw[2:])))
    assert 0x132D358 + 166 * 70 == 0x13300BC
    return dict(source='Z CAM E2-F6 fw 1.0.13 usr/bin/imvt_camera (static extraction)',
                ae_registers=ae, readouts=ro, modes=modes, regs=regs)


def h(v):
    return '' if v == 0xFFFF else f'{v:02X}'


if __name__ == '__main__':
    d = extract(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
    json.dump(d, open(os.path.join(out, 'zcam_imx410_tables.json'), 'w'), indent=1)
    used = sorted({m['readout'] for m in d['modes']})
    with open(os.path.join(out, 'zcam_init_sequence.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['step', 'addr', 'delay_ms_after', 'kind', 'value_hex', 'note'])
        for r in d['regs']:
            v = set(r['val'])
            if r['val'][0] == 0xFFFF and len(v) == 1:
                kind, val = 'delay-only', ''
            elif len(v) == 1:
                kind, val = 'common', f'{r["val"][0]:02X}'
            else:
                kind, val = 'per-readout', ''
            w.writerow([r['order'], f'{r["addr"]:04X}', r['delay_ms'], kind, val, ''])
        for a in d['ae_registers']:
            w.writerow([f'AE{a["idx"]}', f'{a["addr"]:04X}', 0, 'ae-init (exposure/gain state)', '',
                        a['name']])
    with open(os.path.join(out, 'zcam_readout_regs.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['step', 'addr'] + [f'r{r["readout"]}_{r["name"]}_{r["w"]}x{r["h"]}_adc{r["adc_bits"]}'
                                       + ('' if r['readout'] in used else '_UNUSED') for r in d['readouts']])
        for r in d['regs']:
            w.writerow([r['order'], f'{r["addr"]:04X}'] + [h(v) for v in r['val']])
    with open(os.path.join(out, 'zcam_modes.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        keys = list(d['modes'][0])
        w.writerow(keys + ['out_w', 'out_h', 'adc_bits'])
        for m in d['modes']:
            r = d['readouts'][m['readout']]
            w.writerow([m[k] for k in keys] + [r['w'], r['h'], r['adc_bits']])
    with open(os.path.join(out, 'zcam_ae_registers.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['idx', 'addr', 'name', 'flags'])
        for a in d['ae_registers']:
            w.writerow([a['idx'], f'{a["addr"]:04X}', a['name'], hex(a['flags'])])
    print('ok', len(d['modes']), 'modes', len(d['regs']), 'rows', 'used readouts', used)
