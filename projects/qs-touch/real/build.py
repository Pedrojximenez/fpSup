#!/usr/bin/env python3
"""Build genuine native QS additions; no camera I/O."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'fpSup/loader-v4'),str(ROOT/'fpSup/uishare')]
import page as P
import build_v4 as B
import qs_build as QB
from armasm import assemble,symbols

MAGIC=0x314E5351
KEYS=('Format','DC','Res','FPS')


def role(name):
    if name=='FPQS_LegacyFooter':return 7,0
    if name=='FPQS_FooterOn':return 8,0
    if name=='FPQS_FooterText':return 9,0
    if re.fullmatch(r'FPQS_Legacy[1-8]',name):return 1,int(name[-1])-1
    for i,key in enumerate(KEYS):
        prefix='FPQS_'+key
        if name==prefix+'Index':return 3,i
        if name==prefix+'Max':return 4,i
        if name==prefix+'Text':return 5,i
        if name==prefix+'Detail':return 6,i
        if re.fullmatch(prefix+r'On[1-8]',name):return 2,i*8+int(name[-1])-1
    return {'QSN_Active':(10,0),'QSN_Raw':(11,0),'QSN_Input':(12,0),'QSN_Close':(14,0)}.get(name,(13,0))


def data_file():
    patches,pool,info,builder=P.resources()
    out=bytearray(48);strings={}
    def place(data,alignment=4):
        out.extend(bytes(-len(out)%alignment));at=len(out);out.extend(data);return at
    def text(value):
        if value not in strings:strings[value]=place(value.encode()+b'\0',1)
        return strings[value]
    declarations=dict(builder.variables)
    declarations.update({name:dict(type='integer',default=0) for name in
        ('QSN_Active','QSN_Raw','QSN_Input','QSN_Close',*['QSN_'+n for n in P.NATIVE])})
    var_rows=[]
    for name,definition in declarations.items():
        kind=2 if definition['type']=='string' else 0
        first=text(definition['default']) if kind==2 else definition['default']
        r,a=role(name);var_rows.append((kind,text(name),first,r,a))
    names=place(b''.join(struct.pack('<I',text(n)) for n in P.NATIVE))
    labels=('CinemaDNG','MOV','OFF','ON','UHD','FHD',
            '23.98p','24p','25p','29.97p','48p','50p','59.94p','100p','119.88p','RES','FPS',' ')
    label_at=place(b''.join(struct.pack('<I',text(n)) for n in labels))
    var_at=place(b''.join(struct.pack('<5I',*r) for r in var_rows))
    patch_rows=[];refs=[]
    for p in patches:
        at=place(p['data'])
        refs.extend((at+off,text(name)) for off,name in p['refs'])
        patch_rows.append((p['address'],len(p['old']),P.fnv(p['old']),at,len(p['data']),p['records']))
    patch_at=place(b''.join(struct.pack('<6I',*r) for r in patch_rows))
    ref_at=place(b''.join(struct.pack('<2I',*r) for r in refs))
    struct.pack_into('<12I',out,0,0x444E5351,len(out),len(patch_rows),patch_at,len(var_rows),var_at,
                     len(refs),ref_at,len(P.NATIVE),names,len(labels),label_at)
    return bytes(out),dict(info,variable_names=list(declarations),labels=labels)


def sup_file(source=None):
    image=(ROOT/'out/MAIN_c0000000.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()=='92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4'
    data,info=data_file()
    assembly=ROOT/'fpSup/uishare/qs_layer.S'
    layer=assemble(assembly);sym=symbols(assembly)
    defines=[]
    for n in ('qs_entry_record','qs_entry_layout','qs_entry_load','qs_replay_record','qs_replay_layout','qs_replay_load'):
        defines.append(f'-D{n.upper()}={sym[n]&~1}u')
    with tempfile.TemporaryDirectory(prefix='qsn-native-') as d:
        d=Path(d)
        for name in ('qs_apply.c','qs_apply.h','qs_layer.c','qs_layer.h'):
            text=(ROOT/'fpSup/uishare'/name).read_text()
            (d/name).write_text(QB.PUBLIC.sub(r'static \1',text))
        code=B.compile_unit(d,source or HERE/'native.c','sup_entry',
                            [*defines,'-I',str(d),'-I',str(HERE)])
    code_at=80;body=bytearray(32)+code.code
    body.extend(bytes(-len(body)%8));layer_at=48+len(body);body.extend(layer)
    body.extend(bytes(-len(body)%8));data_at=48+len(body);body.extend(data)
    blob=B.make_sup(bytes(body),code_at+code.functions['sup_entry'],'QSN1',min_svc=6,flags=1,name='QS Touch')
    state=(len(blob)+63)&~63
    struct.pack_into('<5I',body,0,MAGIC,state,data_at,len(data),layer_at)
    blob=B.make_sup(bytes(body),code_at+code.functions['sup_entry'],'QSN1',min_svc=6,flags=1,
                    name='QS Touch',block_size=state+4096)
    return blob,dict(code_at=code_at,layer_at=layer_at,data_at=data_at,state_off=state,
                      functions={n:code_at+v for n,v in code.functions.items()},
                      layer_symbols=sym,ui=info)


def build(out,card=False):
    out=Path(out);assert not out.exists(),'Use a new output directory'
    blob,facts=sup_file();out.mkdir(parents=True)
    files={'fpSup/ZQS.BIN':blob}
    if card:
        ar,loader,_=B.boot_card(ui=True,slim=True)
        files.update({'AutoRun.txt':ar,'fpSup/LOADER.BIN':loader,'fpSup/SUPMGR.BIN':B.supmgr_sup()})
        files.update({'fpSup/UI/'+n:d for n,d in B.ui_files().items()})
    for n,data in files.items():
        p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    info=dict(product='Native QS_CINE touch additions',format='FSB4',loader_services=6,
              separate_test_page=False,camera_settings_connected=True,**facts,
              physical_card_written=False,on_camera_verified=False,
              files={n:dict(bytes=len(d),sha256=hashlib.sha256(d).hexdigest()) for n,d in files.items()})
    info['sources']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [HERE/'build.py',HERE/'page.py',HERE/'native.c',HERE/'settings.h',
         ROOT/'fpSup/fpsup-ui/fpsup_ui.c',ROOT/'fpSup/uishare/qs_layer.c',ROOT/'fpSup/uishare/qs_layer.S',
         ROOT/'projects/qs-touch/native/build_tiles.py']}
    (out/'build.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    return info


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--card',action='store_true');a=ap.parse_args()
    print(json.dumps(build(a.out,a.card)['files'],indent=2))
