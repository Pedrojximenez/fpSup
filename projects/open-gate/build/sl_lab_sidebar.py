"""Res Lab's three native tabs: sidebar controls and a shared pixel-scale diagram.

Uses the established frame-guide page, native row/editor templates and allocation
accounting. No additional page hook, loader or recording engine.
"""
import struct
import sl_lab_page as L
import sl_lists as LL

P, SZ, A, BM, N = L.P, L.SZ, L.A, L.BM, L.N
u32, put = L.u32, L.put
X, Y, W, H = 444, 145, 510, 340
MODE_X, MODE_Y, MODE_W = 420, 81, 570
ROW_H = 81
SIDEBAR_W = 358
DOTS = 8


def specs():
    mode = dict(key='MODE', var='SL_M_Sel', list=LL.MODE_NAME,
                title=dict(text=' '), rows=LL.lab_mode_rows(), step=True,
                max_var='SL_ModeMax', summary_var='SL_M_Text', diagram_mode=True)
    def row(key, title, var='SL_E_Button', summary=None, editor=None, choices=None):
        r = dict(key=key, var=var, list=choices or LL.CROP_O_NAME,
                 title=dict(text=' '), rows=LL.CONTROL_FILTERS[choices] if choices else LL.CROP_O_ROWS)
        if summary: r['summary_var'] = summary
        if editor is not None: r['editor'] = editor
        if choices: r['step'] = True
        return r
    return {
        92: [mode]+[row(k,'',v,choices=n) for k,v,n in (
            ('BIT','SL_F_Bit',LL.F_BIT_NAME),('AREA','SL_F_Crop',LL.F_CROP_NAME),
            ('WIDTH','SL_F_Width',LL.F_WIDTH_NAME),('FPS','SL_F_Fps',LL.F_FPS_NAME),
            ('ORDER','SL_F_Prop',LL.F_PROP_NAME))],
        93: [mode,
             dict(row('KEEP', '', summary='SL_C_Text', editor=10), policy='crop'),
             row('BIN', 'Binning H x V', summary='SL_O_Bins', editor=40),
             row('LENS', '', 'SL_O_Lens', choices='SL_LENS'),
             dict(row('OUT', '', summary='SL_O_Size', editor=30), policy='output'),
             row('RATE', '', 'SL_O_RFps', summary='SL_O_Rate', choices=LL.RATE_SEL_NAME)],
        101: [row('NAME', '', summary='SL_E_Name', editor=60),
              dict(row('SAVE', '', summary='SL_E_Text'), save=True)],
    }


def compact(row, mapping, pool, refs, mode=False):
    """Keep popup geometry; fit five single-line rows inside the native body.

    Tab contents inherit the native Menu's 99-pixel Y translation. Static list
    summaries have an extra IconText parent; resizing only the text leaves its
    inherited X offset in the diagram (confirmed on camera, SS__1625/1626).
    """
    objs = {u32(d, 20): u32(d, 24) for d in row if u32(d, 0) == 0x10003}
    popup = {mapping[L.DONOR['lst']], mapping[L.DONOR['scrollbar']]}
    for _ in range(20):
        popup |= {k for k, p in objs.items() if p in popup}
    owner = None
    height=48 if mode else ROW_H
    width=MODE_W if mode else SIDEBAR_W
    scale=width/1024.
    for d in row:
        tag = u32(d, 0)
        if tag == 0x10003: owner = u32(d, 20)
        if owner in popup: continue
        if tag == 0x10004:
            mask, at = u32(d, 28), 32
            if mask & 1:
                x, y = struct.unpack_from('>ff', d, at)
                if owner != mapping[L.DONOR['row']]:
                    struct.pack_into('>ff', d, at, x * scale, y * height / 81.)
                at += 8
            if mask & 2:
                w, h = struct.unpack_from('>ff', d, at)
                struct.pack_into('>ff', d, at, w * scale, h * height / 81.)
            if owner == mapping[L.DONOR['icontext']]:
                assert mask & 3 == 3
                struct.pack_into('>ffff',d,32,16.,16.,300.,44.)
            elif objs.get(owner) == mapping[L.DONOR['icontext']]:
                assert mask & 2 and not mask & 1
                struct.pack_into('>ff',d,32,300.,44.)
        if tag == 0x10005 and pool.text(u32(d, 8)) == 'drawRect':
            mask = u32(d, 28)
            if mask in (0x201,0x203,0x20B):
                at=len(d)-16
                x,y,w,h = struct.unpack_from('>ffff',d,at)
                struct.pack_into('>ffff',d,at,x*scale,y*height/81.,w*scale,h*height/81.)
        if tag == 0x10005 and pool.text(u32(d, 8)) == 'drawText':
            mask = u32(d,28)
            if not mask & 4:
                d[37:37] = struct.pack('>I', 27)
                put(d,28,mask|4);put(d,4,len(d))
            if not mask & 0x10:
                d[41:41]=struct.pack('>I',0);put(d,28,u32(d,28)|0x10);put(d,4,len(d))
            else:put(d,41,0)
            title = owner == mapping[L.DONOR['title_owner']]
            put(d,37,20 if title else 40)
            if mask & 0x40000000:
                struct.pack_into('>ffff',d,len(d)-16,0.,0.,float(width-52),44.)
            base = next(r for r in row if u32(r,0)==0x10004 and u32(r,20)==owner)
            if u32(base,28)&3 == 3:
                struct.pack_into('>ffff',base,32,24. if mode else 16.,0. if title else (4. if mode else 16.),float(width-52),44.)
    if mode:
        root=next(d for d in row if u32(d,0)==0x10004 and u32(d,20)==mapping[L.DONOR['row']])
        if not u32(root,28)&2:
            root[40:40]=bytes(8);put(root,28,u32(root,28)|2);put(root,4,len(root))
        struct.pack_into('>ffff',root,32,float(MODE_X),float(MODE_Y),float(width),48.)
        # Popup remains screen-wide although its closed row moved into the diagram.
        for part in ('lst','scrollbar'):
            base=next(d for d in row if u32(d,0)==0x10004 and u32(d,20)==mapping[L.DONOR[part]])
            x=struct.unpack_from('>f',base,32)[0];struct.pack_into('>f',base,32,x-MODE_X)
            struct.pack_into('>f',base,36,81.-MODE_Y)
        # Replace the closed row's stock pointer/background with two focus arrows.
        cursor=mapping[4251]
        for d in row:
            if u32(d,0)==0x10005 and u32(d,20)==mapping[12]:
                L._intern_at(d,32,'blank',pool,refs)
            if u32(d,0)==0x10005 and u32(d,20) in (mapping[11],mapping[4252]):
                put(d,32,0) # clear the inherited full-width highlight/background
        base=next(d for d in row if u32(d,0)==0x10004 and u32(d,20)==cursor)
        proto=next(d for d in row if u32(d,0)==0x10005 and pool.text(u32(d,8))=='drawRect' and len(d)==52)
        for side in (0,1):
            for dy in range(-7,8):
                r=bytearray(proto);put(r,16,0xffffffff);put(r,20,cursor);put(r,24,20+side*15+dy+7);put(r,32,0x55bbddff)
                struct.pack_into('>ffff',r,len(r)-16,float(6+abs(dy) if not side else width-13-abs(dy)),float(27+dy),3.,2.)
                L._insert_component(row,cursor,base,r)


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


def policy_icons(row, mapping, policy, recs, pool, refs, next_id):
    """Draw native padlocks; do not depend on emoji coverage in the camera font."""
    name=next(i for i,r in enumerate(row) if u32(r,0)==0x10003 and u32(r,20)==mapping[L.DONOR['title_owner']])
    ot,bt,tt=row[name:name+3]
    outline=next(bytearray(r.to_bytes()) for r in recs if r.tag==0x10005 and pool.text(u32(r.to_bytes(),8))=='drawRect' and u32(r.to_bytes(),28)==0x20B)
    added=[];parent=mapping[L.DONOR['row']]
    states=[('SL_O_Lock',False),('SL_C_Open',True)] if policy=='crop' else [('SL_O_Cls',False),('SL_O_Open',True),('SL_O_Auto',None)]
    for var,opened in states:
        oid=next_id;next_id+=1;o,b=bytearray(ot),bytearray(bt)
        put(o,20,oid);put(o,24,parent);put(o,16,0);put(o,8,3 if opened is None else 6)
        put(b,20,oid);struct.pack_into('>ffff',b,32,316.,23.,32.,32.)
        added += [o,b,L._binding(oid,1,var,0,'opacity',pool,refs,1)]
        if opened is None:
            t=bytearray(tt);put(t,20,oid);put(t,24,2);L._intern_at(t,32,'a',pool,refs);put(t,37,29)
            struct.pack_into('>ffff',t,len(t)-16,0.,0.,32.,32.);added.append(t)
        else:
            shapes=[(3,13,21,16),(7,2,13,3),(7,2,3,13),(17,2,3,5 if opened else 13)]
            for k,(x,y,w,h) in enumerate(shapes):
                t=bytearray(outline);put(t,20,oid);put(t,24,2+k);put(t,32,0xffffffff);put(t,36,int(k>0))
                struct.pack_into('>fffff',t,40,2.,float(x),float(y),float(w),float(h));added.append(t)
    # Cyan square identifies the lock/auto field while editing.
    oid=next_id;next_id+=1;o,b=bytearray(ot),bytearray(bt)
    put(o,20,oid);put(o,24,parent);put(o,16,0);put(o,8,3);put(b,20,oid)
    struct.pack_into('>ffff',b,32,313.,20.,36.,36.)
    t=bytearray(outline);put(t,20,oid);put(t,24,1);put(t,32,0x55bbddff);put(t,36,0)
    struct.pack_into('>fffff',t,40,2.,0.,0.,36.,36.)
    added += [o,b,t,L._binding(oid,2,'SL_O_Pad' if policy=='crop' else 'SL_O_Pad2',0,'opacity',pool,refs,1)]
    return added,next_id


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
    def text(label,var,x,y,color=0xffffffff,width=W-32):
        oid,o,b=obj(3 if var else 2,x,y,width,40.)
        t=bytearray(tt[:28])+struct.pack('>I',0x40002015)+bytes(5)+struct.pack('>IIIffff',36,0,color,0.,0.,float(width),40.)
        put(t,4,len(t));put(t,20,oid);put(t,24,1);L._intern_at(t,32,label,pool,refs)
        return [o,b,t]+([L._binding(oid,2,var,1,'text',pool,refs,0)] if var else [])
    def frame(var,color,filled=False):
        oid,o,b=obj(6 if var else 2);r=bytearray(outline);put(r,20,oid);put(r,24,1);put(r,32,color);put(r,36,int(filled))
        struct.pack_into('>fffff',r,40,2.,float(X),float(Y),float(W),float(H))
        return [o,b,r]+([L._binding_sub(oid,2+k,'SL_D_'+var+a,1,'rect',k,pool,refs) for k,a in enumerate('XYWH')] if var else [])
    def solid(x,y,w,h,color):
        oid,o,b=obj(2);r=bytearray(outline);put(r,20,oid);put(r,24,1);put(r,32,color);put(r,36,1)
        struct.pack_into('>fffff',r,40,0.,float(x),float(y),float(w),float(h))
        return [o,b,r]
    # Earlier native siblings paint on top; labels, final, crop, mode, area, dots, sensor.
    # Mode has its own strip above the sensor; SAVE only has a read-only label.
    if parent == 101:
        out+=text(' ','SL_M_Text',MODE_X+24,MODE_Y+4,width=MODE_W-52)
        out+=text('LEFT/RIGHT: position',None,16,259,width=330)
        out+=text('UP/DOWN: character',None,16,340,width=330)
        out+=text('Blank: auto name',None,16,421,width=330)
    out+=text('FPS','SL_D_Fps',X+14,Y+10,width=240)+text('RS','SL_D_Rs',X+265,Y+10,width=W-279)
    out+=text('Mode Corp','SL_D_GTxt',X+14,Y+H-124,0x30d158ff)
    out+=text('Output Corp','SL_D_CTxt',X+14,Y+H-84,0xffd60aff)
    out+=text('Out','SL_D_Final',X+14,Y+H-44,0xff708aff)
    # Earlier siblings paint on top: status belongs before the sensor fill.
    # Full-width status avoids shrinking or clipping saved filenames.
    out+=text('Ready','SL_E_Text',X+14,Y+50,width=W-28)
    out+=frame('F',0xff708aff)+frame('C',0xffd60aff)+frame('R',0x78b8ffff)+frame('G',0x30d158ff)
    for dot in range(8*DOTS):
        oid,o,b=obj(4);r=bytearray(outline);put(r,20,oid);put(r,24,1);put(r,32,0x9a9a9aff);put(r,36,1)
        struct.pack_into('>fffff',r,40,0.,0.,0.,3.,3.)
        out += [o,b,r]+[L._binding_sub(oid,2+k,f'SL_D_L{dot:02d}{a}',1,'rect',k,pool,refs) for k,a in enumerate('XY')]
    out+=frame(None,0x404040ff,True)
    # The stock page has screen-wide grid lines. Mask their right-hand part,
    # leaving a quiet margin around the sensor rather than line fragments.
    out+=solid(SIDEBAR_W,81,1024-SIDEBAR_W,405,0x282828ff)
    # Row backgrounds cover the stock separators. Redraw only the sidebar
    # boundaries, at the native 81-pixel spacing, above those backgrounds.
    dividers=[]
    for i in range(1,6):
        dividers+=solid(0,81+i*ROW_H-2,SIDEBAR_W,2,0x080808ff)
    return out,next_id,dividers


def build(img,pool,refs):
    schemas=P.load_schemas(img);recs=N.split(L.base_page());objs=SZ.objects(recs,pool)
    sub=SZ.subtree(objs,L.DONOR['row']);a,b=SZ.span(recs,objs,sub,L.DONOR['row']);donor=recs[a:b]
    L.STEP_TM.clear();L.STEP_TM.update(L.step_templates(recs,pool))
    tm=L.editor_templates(recs,[],pool,schemas,refs)
    next_id=max(objs)+1;per={};added=[]
    for c,rows in specs().items():
        per[c]=[]
        left_row=0
        for i,spec in enumerate(rows):
            row,mapping,next_id=L.clone_row(donor,sub,spec,81.+left_row*ROW_H,c,pool,schemas,next_id,refs)
            if not spec.get('diagram_mode'):left_row+=1
            bin_label=None
            if spec['key']=='BIN':
                bin_label=next_id;next_id=L.summary_text(row,mapping,'SL_O_BTxt',pool,refs,next_id)
            compact(row,mapping,pool,refs,spec.get('diagram_mode',False))
            if spec.get('save'):
                # SAVE is one large command; the diagram already shows status.
                binding=next(d for d in row if u32(d,0)==0x10006 and len(d)==58 and pool.text(u32(d,8))=='appVariableEvent' and pool.text(u32(d,40))=='SL_E_Text')
                oid=u32(binding,24)
                tx=next(d for d in row if u32(d,0)==0x10005 and u32(d,20)==oid)
                L._intern_at(tx,32,'Save RCD',pool,refs)
                row.remove(binding)
                obj=next(d for d in row if u32(d,0)==0x10003 and u32(d,20)==oid);put(obj,8,u32(obj,8)-1)
            if bin_label:
                base=next(d for d in row if u32(d,0)==0x10004 and u32(d,20)==bin_label)
                struct.pack_into('>ffff',base,32,16.,52.,330.,28.)
                tx=next(d for d in row if u32(d,0)==0x10005 and u32(d,20)==bin_label)
                put(tx,37,28);struct.pack_into('>ffff',tx,len(tx)-16,0.,0.,330.,28.)
            if 'editor' in spec or spec.get('save'):next_id=edit(row,tm,spec.get('editor',0),pool,next_id,spec.get('save',False))
            if spec.get('policy'):
                icons,next_id=policy_icons(row,mapping,spec['policy'],recs,pool,refs,next_id)
                # Earlier siblings paint on top: place icons before the
                # inherited row highlight/background, just like its text.
                first_child=next(j for j,d in enumerate(row[1:],1) if u32(d,0)==0x10003)
                row[first_child:first_child]=icons
            if spec.get('visible'):
                root=u32(row[0],20);base=next(r for r in row if u32(r,0)==0x10004 and u32(r,20)==root)
                for k,prop in enumerate(('opacity','is-active')):
                    L._insert_component(row,root,base,L._binding(root,100+k,spec['visible'],0,prop,pool,refs,1))
            per[c]+=row
        pic,next_id,dividers=drawing(per[c],recs,c,pool,refs,next_id)
        per[c]=dividers+per[c]+pic
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
