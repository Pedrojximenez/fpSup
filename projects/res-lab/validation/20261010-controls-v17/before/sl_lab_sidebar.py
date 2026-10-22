"""Res Lab's three native tabs: sidebar controls and a shared pixel-scale diagram.

Uses the established frame-guide page, native row/editor templates and allocation
accounting. No additional page hook, loader or recording engine.
"""
import struct
import sl_lab_page as L
import sl_lists as LL

P, SZ, A, BM, N = L.P, L.SZ, L.A, L.BM, L.N
u32, put = L.u32, L.put
X, Y, W, H = 390, 81, 600, 400
ROW_H = 49
DOTS = 8


def specs():
    mode = dict(key='MODE', var='SL_M_Sel', list=LL.MODE_NAME,
                title=dict(text='Mode'), rows=LL.lab_mode_rows(), step=True,
                max_var='SL_ModeMax', summary_var='SL_M_Text')
    original = L.rows_spec()
    def row(key, title, var='SL_E_Button', summary=None, editor=None, choices=None):
        r = dict(key=key, var=var, list=choices or LL.CROP_O_NAME,
                 title=dict(text=title), rows=LL.SIDEBAR_LISTS[choices] if choices else LL.CROP_O_ROWS)
        if summary: r['summary_var'] = summary
        if editor is not None: r['editor'] = editor
        if choices: r['step'] = True
        return r
    return {
        92: [mode] + original[92],
        93: [mode,
             row('LOCK', 'Crop shape', 'SL_O_Lock', choices='SL_LOCK'),
             row('KEEP', 'Keep pixels', summary='SL_C_Text', editor=10),
             row('OUT', 'Output pixels', summary='SL_O_Size', editor=30),
             row('BIN', 'Binning H x V', summary='SL_O_Bins', editor=40),
             dict(row('WARP', 'Mode correction', 'MV_SLScale', choices=LL.SCALE_NAME), visible='SL_O_Warp'),
             row('LENS', 'Anamorphic lens', 'SL_O_Lens', choices='SL_LENS'),
             dict(row('FACTOR', 'Lens squeeze', summary='SL_O_Factor', editor=50), visible='SL_O_Lens')],
        101: [mode, dict(row('SAVE', 'Save RCD', summary='SL_E_Text'), save=True)],
    }


def compact(row, mapping, pool):
    """Keep popup geometry; fit eight closed rows inside the 404-pixel body.

    Tab contents inherit the native Menu's 99-pixel Y translation. Static list
    summaries have an extra IconText parent; resizing only the text leaves its
    inherited X offset in the diagram (confirmed on camera, SS__1625/1626).
    """
    objs = {u32(d, 20): u32(d, 24) for d in row if u32(d, 0) == 0x10003}
    popup = {mapping[L.DONOR['lst']], mapping[L.DONOR['scrollbar']]}
    for _ in range(20):
        popup |= {k for k, p in objs.items() if p in popup}
    owner = None
    for d in row:
        tag = u32(d, 0)
        if tag == 0x10003: owner = u32(d, 20)
        if owner in popup: continue
        if tag == 0x10004:
            mask, at = u32(d, 28), 32
            if mask & 1:
                x, y = struct.unpack_from('>ff', d, at)
                if owner != mapping[L.DONOR['row']]:
                    struct.pack_into('>ff', d, at, x * .35, y * ROW_H / 81.)
                at += 8
            if mask & 2:
                w, h = struct.unpack_from('>ff', d, at)
                struct.pack_into('>ff', d, at, w * .35, h * ROW_H / 81.)
            if owner == mapping[L.DONOR['icontext']]:
                assert mask & 3 == 3
                struct.pack_into('>ffff',d,32,14.,23.,326.,25.)
            elif objs.get(owner) == mapping[L.DONOR['icontext']]:
                assert mask & 2 and not mask & 1
                struct.pack_into('>ff',d,32,326.,25.)
        if tag == 0x10005 and pool.text(u32(d, 8)) == 'drawRect':
            mask = u32(d, 28)
            if mask in (0x201,0x203,0x20B):
                at=len(d)-16
                x,y,w,h = struct.unpack_from('>ffff',d,at)
                struct.pack_into('>ffff',d,at,x*.35,y*ROW_H/81.,w*.35,h*ROW_H/81.)
        if tag == 0x10005 and pool.text(u32(d, 8)) == 'drawText':
            mask = u32(d,28)
            if not mask & 4:
                d[37:37] = struct.pack('>I', 24)
                put(d,28,mask|4);put(d,4,len(d))
            title = owner == mapping[L.DONOR['title_owner']]
            put(d,37,22 if title else 24)
            if mask & 0x40000000:
                struct.pack_into('>ffff',d,len(d)-16,0.,0.,326.,25.)
            base = next(r for r in row if u32(r,0)==0x10004 and u32(r,20)==owner)
            if u32(base,28)&3 == 3:
                struct.pack_into('>ffff',base,32,14.,0. if title else 23.,326.,25.)


def edit(row, tm, base, pool, next_id, save=False):
    sel = next(u32(r,20) for r in row if u32(r,0)==0x10003 and pool.text(u32(r,28))=='MenuItem_Select')
    i = 0
    while i < len(row):
        d = row[i]
        if u32(d,0)==0x10006 and u32(d,24)==sel and pool.text(u32(d,8))=='keyEvent' and pool.text(u32(d,20)) in ('Right','OK'):
            n=u32(d,16)
            acts=[tm.write(sel,u32(d,28),1,20 if save else base+5)]
            if not save: acts.append(tm.focus(sel,u32(d,28),2,next_id))
            row[i+1:i+1+n]=acts;put(d,16,len(acts))
        i+=1
    if not save:
        row += tm.editor(next_id,u32(row[0],20),sel,code_base=base)
        next_id+=1
    return next_id


def drawing(template, recs, parent, pool, refs, next_id):
    name = next(i for i,r in enumerate(template) if u32(r,0)==0x10003 and pool.text(u32(r,28))=='Name')
    ot,bt,tt=(template[name+i] for i in range(3))
    outline=next(bytearray(r.to_bytes()) for r in recs if r.tag==0x10005 and pool.text(u32(r.to_bytes(),8))=='drawRect' and u32(r.to_bytes(),28)==0x20B)
    out=[]
    def obj(count, x=0., y=0., w=1024., h=600.):
        nonlocal next_id
        oid=next_id;next_id+=1;o,b=bytearray(ot),bytearray(bt)
        put(o,20,oid);put(o,24,parent);put(o,16,0);put(o,8,count);put(b,20,oid)
        struct.pack_into('>ffff',b,32,x,y,w,h)
        return oid,o,b
    def text(label,var,x,y,color=0xffffffff,width=560):
        oid,o,b=obj(3 if var else 2,x,y,width,32.)
        t=bytearray(tt[:28])+struct.pack('>I',0x40002015)+bytes(5)+struct.pack('>IIIffff',27,0,color,0.,0.,float(width),32.)
        put(t,4,len(t));put(t,20,oid);put(t,24,1);L._intern_at(t,32,label,pool,refs)
        return [o,b,t]+([L._binding(oid,2,var,1,'text',pool,refs,0)] if var else [])
    def frame(var,color,filled=False):
        oid,o,b=obj(6 if var else 2);r=bytearray(outline);put(r,20,oid);put(r,24,1);put(r,32,color);put(r,36,int(filled))
        struct.pack_into('>fffff',r,40,2.,float(X),float(Y),float(W),float(H))
        return [o,b,r]+([L._binding_sub(oid,2+k,'SL_D_'+var+a,1,'rect',k,pool,refs) for k,a in enumerate('XYWH')] if var else [])
    # Earlier native siblings paint on top; labels, final, crop, mode, area, dots, sensor.
    out+=text('Sensor 6064 x 4042',None,X+16,Y+10)
    out+=text(' ','SL_M_Text',X+16,Y+43,0x78b8ffff)
    out+=text(' ','SL_D_Fps',X+16,Y+76,width=280)+text(' ','SL_D_Rs',X+300,Y+76,width=270)
    out+=text(' ','SL_D_GTxt',X+16,Y+H-92,0x30d158ff)
    out+=text(' ','SL_D_CTxt',X+16,Y+H-61,0xffd60aff)
    out+=text(' ','SL_D_Final',X+16,Y+H-30,0xff708aff)
    # Earlier siblings paint on top: status belongs before the sensor fill.
    # Keep it inside the tab clip, beside the sensor label.
    out+=text(' ','SL_E_Text',X+300,Y+10,width=280)
    out+=frame('F',0xff708aff)+frame('C',0xffd60aff)+frame('R',0x78b8ffff)+frame('G',0x30d158ff)
    for dot in range(8*DOTS):
        oid,o,b=obj(4);r=bytearray(outline);put(r,20,oid);put(r,24,1);put(r,32,0x9a9a9aff);put(r,36,1)
        struct.pack_into('>fffff',r,40,0.,0.,0.,3.,3.)
        out += [o,b,r]+[L._binding_sub(oid,2+k,f'SL_D_L{dot:02d}{a}',1,'rect',k,pool,refs) for k,a in enumerate('XY')]
    out+=frame(None,0x404040ff,True)
    return out,next_id


def build(img,pool,refs):
    schemas=P.load_schemas(img);recs=N.split(L.base_page());objs=SZ.objects(recs,pool)
    sub=SZ.subtree(objs,L.DONOR['row']);a,b=SZ.span(recs,objs,sub,L.DONOR['row']);donor=recs[a:b]
    L.STEP_TM.clear();L.STEP_TM.update(L.step_templates(recs,pool))
    tm=L.editor_templates(recs,[],pool,schemas,refs)
    next_id=max(objs)+1;per={};added=[]
    for c,rows in specs().items():
        per[c]=[]
        for i,spec in enumerate(rows):
            row,mapping,next_id=L.clone_row(donor,sub,spec,81.+i*ROW_H,c,pool,schemas,next_id,refs)
            compact(row,mapping,pool)
            if 'editor' in spec or spec.get('save'):next_id=edit(row,tm,spec.get('editor',0),pool,next_id,spec.get('save',False))
            if spec.get('visible'):
                root=u32(row[0],20);base=next(r for r in row if u32(r,0)==0x10004 and u32(r,20)==root)
                for k,prop in enumerate(('opacity','is-active')):
                    L._insert_component(row,root,base,L._binding(root,100+k,spec['visible'],0,prop,pool,refs,1))
            per[c]+=row
        pic,next_id=drawing(per[c],recs,c,pool,refs,next_id);per[c]+=pic
    drop=set();after={}
    for c,rows in L.OLD_ROWS.items():
        for root in rows+L.OLD_EXTRA.get(c,()):
            a,b=SZ.span(recs,objs,SZ.subtree(objs,root),root);drop.update(range(a,b))
        a,b=SZ.span(recs,objs,SZ.subtree(objs,c),c);after[b]=c
    seq=[]
    for i,r in enumerate(recs+[None]):
        if i in after:seq+=per[after[i]]
        if r is not None and i not in drop:seq.append(bytearray(r.to_bytes()))
    titles=L.TAB_TITLES;L.TAB_TITLES={35011:('FILTER',None),35012:('OUTPUT',None),35013:('SAVE',None)}
    try:tab_add,tab_drop=L.tab_titles(seq,[bytearray(r.to_bytes()) for r in donor],pool,refs)
    finally:L.TAB_TITLES=titles
    for old,new in L.PAGE_RENAME.items():
        oldoff=pool.find(old)
        for d in seq:
            for off,kind in P.typed_fields(bytes(d),pool,schemas):
                if kind in ('str','text') and u32(d,off)==oldoff:L._intern_at(d,off,new,pool,refs)
    kids={}
    for d in seq:
        if u32(d,0)==0x10003:kids[u32(d,24)]=kids.get(u32(d,24),0)+1
    for d in seq:
        if u32(d,0)==0x10003:put(d,16,kids.get(u32(d,20),0))
    plus=[A.Record(0,bytes(d)) for rows in per.values() for d in rows]+[A.Record(0,bytes(d)) for d in tab_add]
    minus=[A.Record(0,recs[i].to_bytes()) for i in sorted(drop)]+[A.Record(0,bytes(d)) for d in tab_drop]
    header=A.parse_header(A.Record(0,recs[0].to_bytes()),pool.text);cc=A.component_counts(plus,pool.text)
    for k,v in A.component_counts(minus,pool.text).items():cc[k]=cc.get(k,0)-v
    groups=[r for r in recs if r.tag==0x1000b];donor_groups=[header['groups'][groups.index(r)] for r in donor if r.tag==0x1000b]
    clips=[A.parse_clip(r,pool.text) for r in plus if r.tag==0x1000a]
    delta=dict(objects=sum(r.tag==0x10003 for r in plus)-sum(r.tag==0x10003 for r in minus),component_counts=cc,
               group_budgets=donor_groups*sum(map(len,specs().values())),clip_property_counts=[len(c['properties']) for c in clips],
               property_key_counts=[len(p['keys']) for c in clips for p in c['properties']])
    seq[0]=bytearray(BM.extend_header(A.Record(0,recs[0].to_bytes()),header,delta))
    # Templates can leave relocation records for dropped popup actions.
    live={id(d) for d in seq};refs[:]=[r for r in refs if id(r[0]) in live]
    return seq
