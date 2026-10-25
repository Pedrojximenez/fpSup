"""A private native QS test page: new objects only, no stock QS subtree.

Uses the maintained FT4S packer and native component serializer. The proven
menu input/focus tree is retained behind the new drawing tree. Its animation
requests are removed; passive animation data remains for this hardware trial.
"""
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent / 'native'), str(ROOT / 'fpSup/uishare/tab')]
import build_tiles as B
import build_fp4 as F
import home4_page as H

PAGE, MACHINE = 'FT_QSTOUCH', 'TransQST'
VARS = [(F.VAR_INT, 'QST_Touch', 0), (F.VAR_INT, 'QST_Active', 0),
        (F.VAR_INT, 'QST_Key', 0), (F.VAR_INT, 'QST_X', 0),
        (F.VAR_INT, 'QST_Y', 77), (F.VAR_INT, 'QST_Focus', 0),
        (F.VAR_TEXT, 'QST_Footer', 'UI values only'),
        (F.VAR_TEXT, 'QST_Status', 'QS TOUCH TEST'),
        (F.VAR_INT, 'QST_Bg', 1)]
for k in range(8):
    VARS += [(F.VAR_TEXT, f'QST_N{k}', ' '), (F.VAR_TEXT, f'QST_V{k}', ' '),
             (F.VAR_TEXT, f'QST_D{k}', ' '), (F.VAR_INT, f'QST_On{k}', 0)]
VARS += [(F.VAR_INT, 'QST_Input', 0)]


class Page(B.Builder):
    def build_tiles_only(self):
        self.next_id = 1
        out = []
        rect_src = next(r for r in self.records if B.u32(r, 0) == 0x10005 and
                        self.pool.text(B.u32(r, 8)) == 'drawRect')

        def obj(parent, name, xywh, components):
            oid, rec, base = self.object(parent, name, len(components) + 1)
            x, y, w, h = xywh
            out.extend([rec, self.component(base, oid, 1,
                                           {'position': (x, y), 'size': (w, h), 'is-visible': 1})])
            out.extend(make(oid) for make in components)
            return oid

        def text(local, label, rect, size):
            return lambda oid: self.text(oid, local, label, rect, size)

        def bind(local, name, target, prop, kind='integer'):
            return lambda oid: self.binding(oid, local, name, target, prop, kind=kind,
                                           default=' ' if kind == 'string' else 0)

        root = obj(0, 'QST_ROOT', (0., 0., 1024., 682.), [])
        obj(root, 'QST_BACKGROUND', (0., 0., 1024., 682.), [
            lambda oid: self.component(rect_src, oid, 2, {'color': 0x101315FF, 'do-fill': 1,
                                                         'rect': (0., 0., 1024., 682.)}),
            bind(3, 'QST_Bg', 1, 'is-visible')])
        obj(root, 'QST_HEADER', (0., 0., 1024., 70.), [
            text(2, 'QS TOUCH TEST', (20., 8., 800., 50.), 30),
            bind(3, 'QST_Status', 2, 'text', 'string'),
            text(4, 'BACK', (896., 8., 128., 50.), 28)])
        for k in range(8):
            obj(root, f'QST_CELL{k}', (float(k % 4 * 256), 77. if k < 4 else 308., 256., 223.), [
                text(2, ' ', (10., 22., 236., 40.), 28),
                text(3, ' ', (10., 70., 236., 88.), 36),
                text(4, ' ', (10., 164., 236., 42.), 24),
                bind(5, f'QST_N{k}', 2, 'text', 'string'),
                bind(6, f'QST_V{k}', 3, 'text', 'string'),
                bind(7, f'QST_D{k}', 4, 'text', 'string'),
                bind(8, f'QST_On{k}', 1, 'is-visible')])
        obj(root, 'QST_HIGHLIGHT', (0., 77., 256., 223.), [
            lambda oid: self.component(rect_src, oid, 2, {'color': 0x4CBBD1FF, 'do-fill': 0,
                                                         'border-width': 2., 'rect': (1., 1., 254., 221.)}),
            bind(3, 'QST_Focus', 1, 'is-visible'),
            lambda oid: B.Q.SL._binding_sub(oid, 4, 'QST_X', 1, 'position', 0, self.pool, self.refs),
            lambda oid: B.Q.SL._binding_sub(oid, 5, 'QST_Y', 1, 'position', 1, self.pool, self.refs)])
        obj(root, 'QST_FOOTER', (0., 608., 1024., 74.), [
            text(2, '-', (0., 0., 128., 74.), 40),
            text(3, 'UI values only', (128., 0., 640., 74.), 30),
            text(4, '+', (768., 0., 128., 74.), 40),
            text(5, 'MORE', (896., 0., 128., 74.), 26),
            bind(6, 'QST_Footer', 3, 'text', 'string')])

        # Page lifecycle, not a guessed global screen-name flag. Native screen
        # events write Active at load/unload; the callback gates interception.
        screen_events = [self.records[k] for k in self.tree.comps(1, name='screenEvent')]
        action_src = next(r for r in self.records if B.u32(r, 0) == 0x10009 and
                          self.pool.text(B.u32(r, 8)) == 'controlAppVariable' and len(r) == 46)
        root_rec = out[0]
        extras = []
        # QS_CINE's actual loaded/unloaded events are 1 and 2.
        B.check([B.u32(r, B.Q.fields(r, self.pool, self.schemas)['type'][0])
                 for r in screen_events] == [1, 2], 'Stock page lifecycle changed')
        for local, event_type, value in ((2, 1, '1'), (3, 2, '0')):
            ev = self.component(screen_events[0], 1, local, {'type': event_type})
            B.put(ev, 16, 1)
            act = self.component(action_src, 1, local, {'destination-variable': 'QST_Active', 'value': value})
            B.put(act, 28, 1)
            extras += [ev, act]
        # POST_INT uses the firmware's silent setter: it updates bound
        # components but deliberately skips the C variable subscriber. Relay
        # each raw packet through a native page action, whose notifying setter
        # invokes our GUI-thread callback. Keep the two integer variables
        # separate so unchanged-value suppression cannot eat the event.
        event_src = next(r for r in self.records if B.u32(r, 0) == 0x10006 and
                         self.pool.text(B.u32(r, 8)) == 'appVariableChangeEvent' and len(r) == 41)
        relay_src = next(r for r in self.records if B.u32(r, 0) == 0x10009 and
                         self.pool.text(B.u32(r, 8)) == 'controlAppVariable' and
                         'source-variable' in B.Q.fields(r, self.pool, self.schemas))
        ev = self.component(event_src, 1, 4, {'variable-name': 'QST_Touch', 'type': 2})
        B.put(ev, 16, 1)
        act = self.component(relay_src, 1, 4, {'destination-variable': 'QST_Input',
                             'source-type': 0, 'source-variable': 'QST_Touch'})
        B.put(act, 28, 1)
        extras += [ev, act]
        B.put(root_rec, 8, 4)
        out[2:2] = extras
        # The native compositor paints earlier siblings over later ones.
        # Hardware BG-off comparison confirmed a first-child opaque fill
        # covers the labels and values, so the fill is the last child.
        bg=next(i for i,r in enumerate(out) if B.u32(r,0)==0x10003 and B.u32(r,20)==2)
        end=next(i for i in range(bg+1,len(out)) if B.u32(out[i],0)==0x10003)
        background=out[bg:end];out=out[:bg]+out[end:]+background
        # Child counts and allocations describe only this small private tree.
        objects = {B.u32(r, 20): r for r in out if B.u32(r, 0) == 0x10003}
        for oid, rec in objects.items():
            B.put(rec, 16, sum(B.u32(c, 24) == oid for c in objects.values()))
        old = [B.Q.A.Record(0, bytes(r)) for r in self.records]
        new = [B.Q.A.Record(0, bytes(r)) for r in out]
        new_cc = B.Q.A.component_counts(new, self.pool.text)
        header = B.Q.A.parse_header(old[0], self.pool.text)
        # This is a new page, so it must not reserve QS_CINE's thousands of
        # unused animation groups, clips and key arrays.
        header = dict(header, objects=len(objects), groups=[], clip_property_counts=[], property_key_counts=[],
                      component_counts={k:new_cc.get(k,0) for k in header['component_counts']})
        delta = {'objects': 0, 'component_counts': {},
                 'group_budgets': [], 'clip_property_counts': [], 'property_key_counts': []}
        hdr = B.Q.BM.extend_header(old[0], header, delta)
        out = [bytearray(hdr), *out, bytearray(F.SL.END)]
        at, marks = 0, []
        refs = {}
        for rec, off, name in self.refs:
            refs.setdefault(id(rec), []).append((off, name))
        # Include every string field, including inherited native template names.
        # FT4 replaces only private/new pool offsets; stock references stay stock.
        for rec in out:
            marks.extend((at + off, name) for off, name in refs.get(id(rec), []))
            at += len(rec)
        page = b''.join(out)
        shape = B.Q.P.page_shape(page, self.pool)
        B.check(not shape['orphans'] and not shape['bad_child_counts'], 'Private page tree is invalid')
        return page, marks, {'objects': len(objects), 'bytes': len(page), 'shape': shape}

    def build_private(self):
        # A drawing-only page passed the record parser but failed on hardware.
        # Keep the proven menu focus/key tree (IMX410_FULL_DESIGN r16/r18).
        # Its variables are private and its animation actions are removed.
        tiles, tile_refs, _ = self.build_tiles_only()
        frame, frame_refs, row0 = H.build_home(self.image, self.pool)
        self.frame_row0 = row0

        def records(raw, refs):
            result = [bytearray(r.to_bytes()) for r in B.Q.N.split(raw)]
            mapped = {}
            start = 0
            for r in result:
                mapped[id(r)] = [(off-start, name) for off, name in refs if start <= off < start+len(r)]
                start += len(r)
            return result, mapped

        native, nr = records(frame, frame_refs)
        own, tr = records(tiles, tile_refs)
        # Unlike drawing data, the focus hierarchy remains visible to the
        # native input engine. Our first child draws above the native frame.
        filtered = []
        k = 0
        while k < len(native):
            r = native[k]
            if B.u32(r,0) == 0x10006:
                count = B.u32(r,16)
                actions = native[k+1:k+1+count]
                kept = [a for a in actions if self.pool.text(B.u32(a,8)) != 'controlAnimation']
                B.put(r,16,len(kept))
                filtered += [r,*kept]
                k += 1+count
            else:
                filtered.append(r);k += 1
        native = filtered
        # The native UI engine needs a valid initial focus, even with touch
        # owning our page. No frame variable is shared with the real fpSup UI.
        private_names={name for _kind,name,_value in F.home_vars(row0)}
        for r in native:
            nr[id(r)] = [(off, 'QTG_'+name[3:] if name in private_names else name)
                         for off,name in nr.get(id(r),[])]
        ids = {B.u32(r,20):40000+B.u32(r,20) for r in own if B.u32(r,0)==0x10003}
        for r in own[1:-1]:
            tag=B.u32(r,0)
            if tag==0x10003:
                old,parent=B.u32(r,20),B.u32(r,24)
                B.put(r,20,ids[old]);B.put(r,24,ids[parent] if parent else 1)
            elif tag in B.Q.BM.OWNER_OFFSETS:
                off=B.Q.BM.OWNER_OFFSETS[tag]
                B.put(r,off,ids[B.u32(r,off)])
        root=next(r for r in native if B.u32(r,0)==0x10003 and B.u32(r,20)==1)
        B.put(root,16,B.u32(root,16)+1)
        first_child=next(i for i,r in enumerate(native) if B.u32(r,0)==0x10003 and B.u32(r,24)==1)
        seq=[*native[:first_child],*own[1:-1],*native[first_child:]]
        new=[B.Q.A.Record(0,bytes(r)) for r in seq]
        counts=B.Q.A.component_counts(new,self.pool.text)
        header=B.Q.A.parse_header(new[0],self.pool.text)
        header=dict(header,objects=header['objects']+len(ids),
                    component_counts={n:counts.get(n,0) for n in header['component_counts'] | counts})
        hdr=B.Q.BM.extend_header(new[0],header,{'objects':0,'component_counts':{},'group_budgets':[],
                                              'clip_property_counts':[],'property_key_counts':[]})
        seq[0]=bytearray(hdr)
        marks=[];at=0
        for r in seq:
            marks += [(at+off,name) for off,name in (nr.get(id(r),[]) or tr.get(id(r),[]))]
            at += len(r)
        raw=b''.join(seq)
        shape=B.Q.P.page_shape(raw,self.pool)
        B.check(not shape['orphans'] and not shape['bad_child_counts'],'Invalid focus/tiles tree')
        B.check(counts.get('controlAnimation',0)==0,'Animation requests remain')
        return raw,marks,{'objects':header['objects'],'own_objects':len(ids),
                          'native_focus_objects':header['objects']-len(ids),'bytes':len(raw),
                          'animation_requests':0,'passive_animation_data':True,'shape':shape}


def data_file():
    p = Page((ROOT / 'out/MAIN_c0000000.bin').read_bytes())
    page, refs, info = p.build_private()
    frame_vars=[]
    for kind,name,value in F.home_vars(p.frame_row0):
        value = p.frame_row0 if name=='FT_Focus' else 0 if name=='FT_Title' else 1 if name=='FT_Visible0' else value
        frame_vars.append((kind,'QTG_'+name[3:],value))
    data, pack = F.ft4_file([(PAGE, (page, refs))], ((PAGE, 'FT_Y6', 'Return'),), MACHINE,
                            VARS+frame_vars, ('QS Touch test', PAGE, 'FT_Y6', 'QS TOUCH TEST',
                                   'UI values only', ' ', 'FORMAT', 'DC', 'RES', 'FPS',
                                   'MOV', 'CDNG 8bit', 'CDNG 10bit', 'CDNG 12bit', 'CDNG 14bit',
                                   'OG', 'HD', 'S35', 'APS-C',
                                   '1K', '2K', '3K', '3.5K', '4K',
                                   '23.98p', '24p', '25p', '29.97p', '50p', '59.94p',
                                   'FORMAT options', 'DC options', 'RES options', 'FPS options'))
    return data, {**info, 'pack_info': pack}
