#!/usr/bin/env python3
"""The private tiles with immediate touch-state bindings, no new animation clips."""
import argparse
import json
from pathlib import Path
import build_tiles as B


class TouchBuilder(B.Builder):
    def attach(self, owner, records):
        self.inserts.setdefault(self.tree.block(owner)[-1], []).extend(records)
        self.added.extend(records)
        B.put(self.tree.obj(owner), 8, B.u32(self.tree.obj(owner), 8) + len(records))

    def route_inputs(self, holders, more):
        super().route_inputs(holders, more)
        root_base = self.template(1, 'objectBase')
        local = max(B.Q.local_ids(self.tree, 1)) + 1
        self.attach(1, [self.binding(1, local, 'FPQS_PanelOn', B.u32(root_base, 24), 'is-visible')])
        self.legacy_gate(10060, 'FPQS_TouchLegacyCursor')
        # The v1 footer is also new, so it is not in the immutable source Tree.
        footer = next(r for r in self.added if B.u32(r, 0) == 0x10003 and
                      self.pool.text(B.u32(r, 28)) == 'FPQS_Footer')
        footer_id = B.u32(footer, 20)
        gate = self.binding(footer_id, 5, 'FPQS_TouchLegacyFooter', 1, 'opacity', default=1)
        self.inserts[self.tree.block(299)[-1]].append(gate)
        self.added.append(gate)
        B.put(footer, 8, B.u32(footer, 8) + 1)

        # A new highlight: its integer x/y bindings snap, with no animation curve.
        oid, obj, base = self.object(1, 'FPQS_TouchFocus', 5)
        base = self.component(base, oid, 1, {'position': (0., 77.), 'size': (256., 223.), 'is-visible': 0})
        donor = next(r for r in self.records if B.u32(r, 0) == 0x10005 and
                     self.pool.text(B.u32(r, 8)) == 'drawRect')
        rect = self.component(donor, oid, 2, {'color': 0xFFFFFFFF, 'do-fill': 0,
                                            'border-width': 2., 'rect': (1., 1., 254., 221.)})
        on = self.binding(oid, 3, 'FPQS_TouchFocusOn', 1, 'is-visible')
        axes = []
        for local, name, axis, default in ((4, 'FPQS_TouchFocusX', 0, 0), (5, 'FPQS_TouchFocusY', 1, 77)):
            self.var(name, default=default)
            axes.append(B.Q.SL._binding_sub(oid, local, name, 1, 'position', axis, self.pool, self.refs))
        self.insert_child(1, [obj, base, rect, on, *axes])

        oid, obj, base = self.object(299, 'FPQS_TouchFooter', 7)
        base = self.component(base, oid, 1, {'position': (0., 0.), 'size': (1024., 74.), 'is-visible': 0})
        self.insert_child(299, [obj, base,
            self.text(oid, 2, '-', (0., 0., 128., 74.), 40),
            self.text(oid, 3, ' ', (128., 0., 640., 74.), 32),
            self.text(oid, 4, '+', (768., 0., 128., 74.), 40),
            self.text(oid, 5, 'MORE', (896., 0., 128., 74.), 26),
            self.binding(oid, 6, 'FPQS_TouchFooterOn', 1, 'is-visible'),
            self.binding(oid, 7, 'FPQS_TouchFooterText', 3, 'text', kind='string', default=' ')])
        oid, obj, base = self.object(1, 'FPQS_TouchPages', 3)
        base = self.component(base, oid, 1, {'position': (900., 8.), 'size': (116., 54.), 'is-visible': 1})
        self.insert_child(1, [obj, base, self.text(oid, 2, '1/1', (0., 0., 116., 54.), 26),
                             self.binding(oid, 3, 'FPQS_TouchPageText', 2, 'text', kind='string', default='1/1')])
        self.report['touch'] = {
            'animation': False,
            'native_geometry': {'width': 1024, 'height': 682, 'row_y': [77, 308], 'cell': [256, 223], 'footer_y': 608},
            'input': 'normalized DOWN/MOVE/UP/CANCEL, one contact; not native raw flag decoding',
            'page_change': 'request to the layout owner; no automatic source-page installation',
            'details': 'MORE emits a private intent; native detail contents require their own adapter',
        }


def build(image=None):
    image = image if image is not None else (B.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
    page, pool, report = TouchBuilder(image).build()
    report['status'] = 'offline touch resource and normalized-event controller; no camera installation'
    return page, pool, report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    out = ap.parse_args().out
    B.check(not out.exists(), 'Use a new output directory')
    page, pool, report = build()
    out.mkdir(parents=True)
    (out / 'QS_CINE.fpqs-touch.page').write_bytes(page)
    (out / 'QS_CINE.fpqs-touch.strings').write_bytes(pool.data)
    (out / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'Built {report["new_objects"]} new objects, {len(report["variables"])} private variables, no new animation clips')
