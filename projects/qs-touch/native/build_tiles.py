#!/usr/bin/env python3
"""Build independent QS tile objects in a private page; offline resource only.

No AutoRun, installer, USB, firmware mutation or camera settings writes.
The output still needs a registered-variable / recording-service adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'projects/open-gate/build/res-qs'))
import qs_page as Q

u32, put, check = Q.u32, Q.put, Q.check
PIN = 'a2a474aa2e1d7354cb0920c5b81443c2fe1ee8855a5562a6c86c6700bea50d5d'
TILES = (('Format', 'FORMAT', 20), ('DC', 'DC', 17),
         ('Res', 'RES', 21), ('FPS', 'FPS', 22))
EVENT_ROLES = {str(ui - 1): key for key, _, ui in TILES}
DIALS = (253, 255, 256, 257)
AEL = 8514


def blocks(tree, owner, name):
    """One event and its actions, without the next event or animation record."""
    own = tree.block(owner)[1:]
    hits = [i for i in own if u32(tree.recs[i], 0) == 0x10006 and
            tree.pool.text(u32(tree.recs[i], 20)) == name]
    check(len(hits) == 1, f'{owner}/{name}: expected one event')
    event = hits[0]
    actions = []
    for index in own[own.index(event) + 1:]:
        if u32(tree.recs[index], 0) != 0x10009:
            break
        actions.append(index)
    return event, actions


class Builder:
    def __init__(self, image):
        self.image = image
        self.stock = Q.stock_page(image)
        check(hashlib.sha256(self.stock).hexdigest() == PIN, 'QS_CINE fingerprint mismatch')
        self.pool = Q.P.Pool(Q.stock_pool(image))
        self.schemas = Q.P.load_schemas(image)
        self.records = [bytearray(r.to_bytes()) for r in Q.N.split(self.stock)]
        self.tree = Q.Tree(self.records, self.pool)
        self.refs, self.inserts, self.removed = [], {}, set()
        self.added, self.variables = [], {}
        self.next_id = max(self.tree.at) + 1
        self.report = {'tiles': [], 'dials': [], 'more': [], 'legacy_gates': []}

    def var(self, name, kind='integer', default=0):
        old = self.variables.setdefault(name, {'type': kind, 'default': default})
        check(old == {'type': kind, 'default': default}, 'Conflicting variable declaration')
        return name

    def intern(self, rec, offset, value):
        Q.SL._intern_at(rec, offset, value, self.pool, self.refs)

    def component(self, template, owner, local, changes):
        """Serialize native fields by schema; preserve unmodified donor fields."""
        tag = u32(template, 0)
        schema = self.schemas[self.pool.text(u32(template, 8))]
        old = Q.fields(template, self.pool, self.schemas)
        check(set(changes) <= {p['name'] for p in schema}, 'Unknown component property')
        values = {name: bytes(template[off:off + Q.SIZE[kind]])
                  for name, (off, kind) in old.items()}
        for prop in schema:
            name, kind = prop['name'], prop['kind']
            if name not in changes:
                continue
            value = changes[name]
            if isinstance(value, str):
                check(kind in (9, 10, 11, 12, 13), f'{name}: not a string property')
                offset, _ = self.pool.intern(value)
                values[name] = struct.pack('>I', offset) + (b'\0' if kind == 11 else b'')
            elif isinstance(value, tuple):
                values[name] = struct.pack('>' + 'f' * len(value), *value)
            elif kind == 1:
                values[name] = struct.pack('>f', value)
            else:
                values[name] = struct.pack('>I', value)
            check(len(values[name]) == Q.SIZE[kind], f'{name}: wrong field width')
        out = bytearray(template[:Q.BM.MASK_OFFSETS[tag]])
        for start in range(0, len(schema), 32):
            group = schema[start:start + 32]
            out.extend(struct.pack('>I', sum(1 << n for n, p in enumerate(group) if p['name'] in values)))
            for prop in group:
                if prop['name'] in values:
                    at = len(out)
                    out.extend(values[prop['name']])
                    if isinstance(changes.get(prop['name']), str):
                        self.refs.append((out, at, changes[prop['name']]))
        put(out, 4, len(out))
        put(out, Q.BM.OWNER_OFFSETS[tag], owner)
        put(out, Q.BM.OWNER_OFFSETS[tag] + 4, local)
        return out

    def template(self, owner, component):
        found = self.tree.comps(owner, name=component)
        check(len(found) == 1, f'{owner}: expected one {component}')
        return self.records[found[0]]

    def binding(self, owner, local, name, target, prop, reverse=0, default=0, kind='integer'):
        self.var(name, kind, default)
        return Q.SL._binding(owner, local, name, target, prop, self.pool, self.refs, reverse)

    def object(self, parent, name, count, base=None):
        oid = self.next_id
        self.next_id += 1
        check(oid < 0x10000, 'Object namespace exhausted')
        obj = bytearray(self.tree.obj(7914))
        for off, value in ((8, count), (16, 0), (20, oid), (24, parent)):
            put(obj, off, value)
        self.intern(obj, 28, name)
        source_base = base if base is not None else self.template(7914, 'objectBase')
        return oid, obj, source_base

    def insert_child(self, parent, records):
        after = self.tree.block(parent)[-1]
        self.inserts.setdefault(after, []).extend(records)
        put(self.tree.obj(parent), 16, u32(self.tree.obj(parent), 16) + 1)
        self.added.extend(records)

    def holder(self, key, more=False):
        name = f'FPQS_{key}' + ('More' if more else 'Index')
        oid, obj, base = self.object(299, name, 4)
        base = self.component(base, oid, 1, {'position': (0., 0.), 'size': (0., 0.), 'is-visible': 0})
        ctl = self.component(self.template(341, 'controlValue'), oid, 2,
                             {'min-value': 0., 'max-value': 65535. if more else 0.,
                              'value': 0., 'is-value-loop': int(more)})
        binding = self.binding(oid, 3, name, 2, 'value', reverse=1)
        extra = [] if more else [self.binding(oid, 4, f'FPQS_{key}Max', 2, 'max-value')]
        put(obj, 8, 3 + len(extra))
        self.insert_child(299, [obj, base, ctl, binding, *extra])
        return oid

    def text(self, owner, local, label, rect, size, color=0xFFFFFFFF, single_line=1):
        return self.component(self.template(Q.TEXT_DONOR, 'drawText'), owner, local,
                              {'text': label, 'font-size': size, 'rect': rect,
                               'is-single-line': single_line, 'color': color})

    def tile(self, cell, parent, key, title):
        oid, obj, base = self.object(parent, f'FPQS_{key}_{cell}', 7)
        base = self.component(base, oid, 1, {'position': (0., 0.), 'size': (256., 223.), 'is-visible': 0})
        title_rec = self.text(oid, 2, title, (12., 22., 232., 40.), 28)
        value_rec = self.text(oid, 3, ' ', (12., 70., 232., 88.), 36, single_line=0)
        detail_rec = self.text(oid, 4, ' ', (12., 164., 232., 42.), 26, 0xCCCCCCFF)
        on = self.binding(oid, 5, f'FPQS_{key}On{cell}', 1, 'is-visible')
        value = self.binding(oid, 6, f'FPQS_{key}Text', 3, 'text', kind='string', default=' ')
        detail = self.binding(oid, 7, f'FPQS_{key}Detail', 4, 'text', kind='string', default=' ')
        self.insert_child(parent, [obj, base, title_rec, value_rec, detail_rec, on, value, detail])
        self.report['tiles'].append({'key': key, 'cell': cell, 'object': oid, 'parent': parent})

    def legacy_gate(self, owner, name):
        base = self.template(owner, 'objectBase')
        local = max(Q.local_ids(self.tree, owner)) + 1
        gate = self.binding(owner, local, name, u32(base, 24), 'opacity', default=1)
        self.inserts.setdefault(self.tree.block(owner)[-1], []).append(gate)
        self.added.append(gate)
        put(self.tree.obj(owner), 8, u32(self.tree.obj(owner), 8) + 1)
        self.report['legacy_gates'].append({'object': owner, 'variable': name})

    def action(self, source, owner, local, target, formula):
        return self.component(source, owner, local,
                              {'object-id': target, 'formula': formula})

    def route_inputs(self, holders, more):
        action_template = self.records[blocks(self.tree, 253, '19')[1][0]]
        for dial in DIALS:
            for event, key in EVENT_ROLES.items():
                _, actions = blocks(self.tree, dial, event)
                check(len(actions) == 1, 'Unexpected dial action chain')
                old = self.records[actions[0]]
                formula = 'dst + 1' if dial in (253, 257) else 'dst - 1'
                source = old if self.pool.text(u32(old, 8)) == 'changePropertyByControl' else action_template
                self.records[actions[0]] = self.action(source, dial, u32(old, 24), holders[key], formula)
                self.report['dials'].append({'owner': dial, 'event': event, 'target': holders[key], 'formula': formula})
        # Replace the full AEL action chains: no menu setters, jump or timer survives.
        for event, key in EVENT_ROLES.items():
            if key == 'DC':
                continue
            _, actions = blocks(self.tree, AEL, event)
            self.records[actions[0]] = self.action(action_template, AEL, u32(self.records[actions[0]], 24),
                                                  more[key], 'dst + 1')
            self.removed.update(actions[1:])
            self.report['more'].append({'owner': AEL, 'event': event, 'target': more[key]})
        # Stock DC has no AEL event. Give our DC its own event and private gate.
        source = self.records[blocks(self.tree, AEL, '19')[0]]
        local = max(Q.local_ids(self.tree, AEL)) + 1
        event = self.component(source, AEL, local, {'type': 0})
        self.intern(event, 20, 'FPQS_DC_MoreKey')
        action = self.action(action_template, AEL, local, more['DC'], 'dst + 1')
        gate = self.binding(AEL, local + 1, 'FPQS_DCMoreKeyOn', local, 'type')
        self.inserts.setdefault(self.tree.block(AEL)[-1], []).extend([event, action, gate])
        self.added.extend([event, action, gate])
        put(self.tree.obj(AEL), 8, u32(self.tree.obj(AEL), 8) + 2)
        self.report['more'].append({'owner': AEL, 'event': 'FPQS_DC_MoreKey', 'target': more['DC']})

    def build(self):
        holders = {key: self.holder(key) for key, _, _ in TILES}
        more = {key: self.holder(key, more=True) for key, _, _ in TILES}
        for n, root, icon02, _ in Q.cells(self.tree):
            self.legacy_gate(self.tree.child(root, 'Icon01'), f'FPQS_Legacy{n}')
            self.legacy_gate(icon02, f'FPQS_Legacy{n}')
            for key, title, _ in TILES:
                self.tile(n, root, key, title)
        self.legacy_gate(339, 'FPQS_LegacyFooter')
        oid, obj, base = self.object(299, 'FPQS_Footer', 4)
        base = self.component(base, oid, 1, {'position': (0., 0.), 'size': (1024., 74.), 'is-visible': 0})
        self.insert_child(299, [obj, base, self.text(oid, 2, ' ', (40., 11., 944., 54.), 30),
                               self.binding(oid, 3, 'FPQS_FooterOn', 1, 'is-visible'),
                               self.binding(oid, 4, 'FPQS_FooterText', 2, 'text', kind='string', default=' ')])
        self.route_inputs(holders, more)
        # Recompute changes from records, including removed native action kinds.
        removed = [Q.A.Record(0, bytes(self.records[k])) for k in self.removed]
        added_counts = Q.A.component_counts([Q.A.Record(0, bytes(r)) for r in self.added], self.pool.text)
        removed_counts = Q.A.component_counts(removed, self.pool.text)
        # DC's four native controlAppState actions become changePropertyByControl.
        added_counts['changePropertyByControl'] += 4 + 3
        removed_counts['controlAppState'] = removed_counts.get('controlAppState', 0) + 4
        removed_counts['controlAppVariable'] = removed_counts.get('controlAppVariable', 0) + 3
        delta_counts = {name: added_counts.get(name, 0) - removed_counts.get(name, 0)
                        for name in added_counts.keys() | removed_counts.keys()}
        header = Q.A.parse_header(Q.A.Record(0, bytes(self.records[0])), self.pool.text)
        delta = {'objects': self.next_id - max(self.tree.at) - 1, 'component_counts': delta_counts,
                 'group_budgets': [], 'clip_property_counts': [], 'property_key_counts': []}
        self.records[0] = bytearray(Q.BM.extend_header(Q.A.Record(0, bytes(self.records[0])), header, delta))
        out = []
        for k, rec in enumerate(self.records):
            if k not in self.removed:
                out.append(rec)
            out.extend(self.inserts.get(k, []))
        offsets, cursor = {}, 0
        for rec in out:
            offsets[id(rec)] = cursor
            cursor += len(rec)
        marks = [(offsets[id(rec)] + off, name) for rec, off, name in self.refs]
        page = b''.join(bytes(r) for r in out)
        self.report.update(new_objects=delta['objects'], holders=holders, more_holders=more,
                           variables=self.variables, marks=sorted(marks), source_sha256=PIN,
                           page_sha256=hashlib.sha256(page).hexdigest(), bytes=len(page),
                           status='offline resource candidate; no runtime installation or touch input adapter',
                           install_precondition='register and initialize all declared variables before publishing the page',
                           limits=['Native parser validation does not execute bindings, painting, touch or settings services',
                                   'Do not install without a UI-thread lifecycle and recording-service adapter'])
        return page, self.pool, self.report


def build(image=None):
    image = image if image is not None else (ROOT / 'out/MAIN_c0000000.bin').read_bytes()
    return Builder(image).build()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    check(not args.out.exists(), 'Use a new output directory')
    page, pool, report = build()
    args.out.mkdir(parents=True)
    (args.out / 'QS_CINE.fpqs.page').write_bytes(page)
    (args.out / 'QS_CINE.fpqs.strings').write_bytes(pool.data)
    (args.out / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'Built {len(report["tiles"])} independent tile instances; {report["new_objects"]} new objects; {len(page)} bytes')


if __name__ == '__main__':
    main()
