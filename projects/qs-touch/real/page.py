"""Native QS_CINE additions as a guarded sparse record stream.

The original QS name, GUI id 159, view objects, lifecycle and native setting
subscribers remain in use. Unmodified records keep their original positions,
so Res-Custom's existing QS recipe still sees them. This is not FT_QSTOUCH.
"""
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent/'native')]
import build_tiles as B

NATIVE = ('MV_RecordingFormat', 'CM_DCCrop', 'MV_Resolution', 'MV_FrameRate',
          'MV_DNGQuality', 'MV_MOVQuality', 'QS_FocusPos',
          *[f'MV_QSMENU_QS{k}' for k in range(1, 9)])


def fnv(data):
    value = 0x811C9DC5
    for c in data:
        value = ((value ^ c)*0x01000193) & 0xFFFFFFFF
    return value


class NativePage(B.Builder):
    def route_inputs(self, holders, more):
        # Leave the ONE native controlValue owner for every setting intact.
        # Duplicate two-way holders can publish their initial value over the
        # native mirror. Original dial / AEL actions and Res-Custom's edits
        # continue to use the native holders, with no extra input owner.
        self.add_root_events()

    def add_root_events(self):
        owner = 1
        end = self.tree.block(owner)[-1]
        local = max(B.Q.local_ids(self.tree, owner)) + 1
        change = next(r for r in self.records if B.u32(r, 0) == 0x10006 and
                      self.pool.text(B.u32(r, 8)) == 'appVariableChangeEvent' and len(r) == 41)
        actions = [r for r in self.records if B.u32(r, 0) == 0x10009 and
                   self.pool.text(B.u32(r, 8)) == 'controlAppVariable']
        literal = next(r for r in actions if len(r) == 46)
        copy = next(r for r in actions if 'source-variable' in B.Q.fields(r, self.pool, self.schemas))
        lifecycle = [self.records[k] for k in self.tree.comps(1, name='screenEvent')]
        additions = []

        def event(source, fields, action_source, action_fields):
            nonlocal local
            ev = self.component(source, owner, local, fields)
            act = self.component(action_source, owner, local, action_fields)
            B.put(ev, 16, 1); B.put(act, 28, 1)
            additions.extend((ev, act)); local += 1

        for kind, value in ((1, '1'), (2, '0')):
            event(lifecycle[0], {'type': kind}, literal,
                  {'destination-variable': 'QSN_Active', 'value': value})
        event(change, {'variable-name': 'QSN_Raw', 'type': 2}, copy,
              {'destination-variable': 'QSN_Input', 'source-type': 0, 'source-variable': 'QSN_Raw'})
        # A private mirror informs our painter, while the stock subscriber
        # remains exclusively owned by UicGuiMenuQs.
        for name in NATIVE:
            event(change, {'variable-name': name, 'type': 2}, copy,
                  {'destination-variable': 'QSN_'+name, 'source-type': 0, 'source-variable': name})
        close = self.component(change, owner, local, {'variable-name':'QSN_Close', 'type':2})
        B.put(close,16,1)
        # Original QS's app-sync-request 0 leaves through the native GUI owner.
        source = next(r for r in self.records if B.u32(r,0)==0x10009 and
                      self.pool.text(B.u32(r,8))=='controlAppState' and B.u32(r,32)==0x22)
        action = self.component(source,owner,local,{})
        B.put(action,28,1);additions += [close,action]
        self.inserts.setdefault(end, []).extend(additions)
        self.added.extend(additions)
        B.put(self.tree.obj(owner), 8, B.u32(self.tree.obj(owner), 8)+len(additions)//2)

    def build(self):
        holders = dict(Format=341, DC=312, Res=343, FPS=345)
        for n, root, icon, _ in B.Q.cells(self.tree):
            self.legacy_gate(self.tree.child(root, 'Icon01'), f'FPQS_Legacy{n}')
            self.legacy_gate(icon, f'FPQS_Legacy{n}')
            for key, title, _ in B.TILES:self.tile(n, root, key, title)
        self.legacy_gate(339, 'FPQS_LegacyFooter')
        oid, obj, base = self.object(299, 'FPQS_Footer', 6)
        base = self.component(base, oid, 1, {'position':(0.,0.), 'size':(1024.,74.), 'is-visible':0})
        self.insert_child(299, [obj, base, self.text(oid, 2, ' ', (128.,11.,640.,54.), 30),
            self.binding(oid, 3, 'FPQS_FooterOn', 1, 'is-visible'),
            self.binding(oid, 4, 'FPQS_FooterText', 2, 'text', kind='string', default=' '),
            self.text(oid,5,'-',(0.,0.,128.,74.),40),
            self.text(oid,6,'+',(768.,0.,128.,74.),40)])
        self.route_inputs(holders, {})
        pool, report = self.pool, self.report
        out = []
        for k, r in enumerate(self.records):
            if k not in self.removed:out.append(r)
            out.extend(self.inserts.get(k, []))
        stock = [B.Q.A.Record(0, r.to_bytes()) for r in B.Q.N.split(self.stock)]
        actual = [B.Q.A.Record(0, bytes(r)) for r in out]
        counts = B.Q.A.component_counts(actual, pool.text)
        header = B.Q.A.parse_header(stock[0], pool.text)
        obj_count = sum(r.tag == 0x10003 for r in actual)
        header = dict(header, objects=obj_count,
                      component_counts={n: counts.get(n, 0) for n in header['component_counts'] | counts})
        self.records[0] = bytearray(B.Q.BM.extend_header(stock[0], header,
            {'objects':0, 'component_counts':{}, 'group_budgets':[],
             'clip_property_counts':[], 'property_key_counts':[]}))
        report.update(holders=holders, variables=self.variables, new_objects=obj_count-955)
        report['native_settings'] = NATIVE[:4]
        report['page'] = 'QS_CINE'
        report['gui_id'] = 159
        report['separate_test_page'] = False
        report['camera_settings_connected'] = True
        return pool, report


def resources():
    image = (ROOT/'out/MAIN_c0000000.bin').read_bytes()
    builder = NativePage(image)
    pool, report = builder.build()
    old = B.Q.N.split(builder.stock)
    patches = []
    for k, record in enumerate(old):
        records = ([] if k in builder.removed else [builder.records[k]]) + builder.inserts.get(k, [])
        data = b''.join(bytes(r) for r in records)
        if data == record.to_bytes():continue
        refs, at = {}, 0
        for r in records:
            refs.update((at+off, name) for ref, off, name in builder.refs if ref is r)
            at += len(r)
        patches.append(dict(address=B.Q.SET_START+record.offset, old=record.to_bytes(),
                            data=data, records=len(records), refs=list(refs.items())))
    # None of our record replacements may mask Res-Custom's existing recipe.
    import json
    recipe = json.loads((ROOT/'fpSup/uishare/ui/qs_recipe.json').read_text())
    other = {int(row['address'], 16) for row in recipe['records']}
    B.check(not other.intersection(p['address'] for p in patches), 'Res-Custom record overlap')
    report.update(patches=len(patches), res_custom_record_overlap=False)
    return patches, pool, report, builder
