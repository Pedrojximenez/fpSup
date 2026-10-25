#!/usr/bin/env python3
"""Build QSTOUCH.BIN, a native Loader v4 touch/UI test sup. Offline only."""
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
sys.path[:0]=[str(HERE),str(ROOT/'fpSup/loader-v4')]
import build_v4 as B
import page as P
FIRMWARE_SHA256='92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4'


def private_core(tmp):
    """Internalize the unchanged portable core in a single -fropi unit.

    No second implementation of gestures. Unused publication helpers are
    removed by the compiler; the sup publishes through its private FT4 page.
    """
    core=HERE.parent/'core'
    for name in ('qs_tiles.h','qs_tiles.c','qs_tiles_touch.h','qs_tiles_touch.c'):
        data=(core/name).read_text()
        data=re.sub(r'^(int|void|QttResult) (qt\w*\s*\()',r'static \1 \2',data,flags=re.M)
        (tmp/name).write_text(data)
    data='''
/* Compiler-generated aggregate copies are local and bounded by their caller. */
static void *memcpy(void *dst,const void *src,unsigned n) {
    unsigned char *d=dst;const unsigned char *s=src;while(n--)*d++=*s++;return dst;
}
static void *memset(void *dst,int v,unsigned n) {
    unsigned char *d=dst;while(n--)*d++=(unsigned char)v;return dst;
}
__attribute__((used)) static void __aeabi_memclr4(void *dst,unsigned n) { memset(dst,0,n); }
__attribute__((used)) static void __aeabi_memclr(void *dst,unsigned n) { memset(dst,0,n); }
__attribute__((used)) static void __aeabi_memcpy4(void *dst,const void *src,unsigned n) { memcpy(dst,src,n); }
__attribute__((used)) static void __aeabi_memcpy(void *dst,const void *src,unsigned n) { memcpy(dst,src,n); }
#include "qs_tiles.c"
#include "qs_tiles_touch.c"
'''
    (tmp/'private_core.c').write_text(data)


def sup_file(source=None):
    image=(ROOT/'out/MAIN_c0000000.bin').read_bytes()
    if hashlib.sha256(image).hexdigest()!=FIRMWARE_SHA256:
        raise ValueError('SUP ABI requires the pinned SIGMA fp 5.02 image')
    if struct.unpack_from('<I',image,0xCFCCDC)[0]!=0xC05131A0:
        raise ValueError('Unexpected native touch observer slot')
    ui,ui_info=P.data_file()
    with tempfile.TemporaryDirectory(prefix='qstouch-sup-') as d:
        tmp=Path(d);private_core(tmp)
        text=B.compile_unit(tmp,source or HERE/'touch_sup.c','sup_entry',['-I',str(tmp)])
    code_off=64
    body=bytearray(16)+text.code
    body.extend(bytes(-len(body)%8))
    ui_off=48+len(body);body.extend(ui)
    probe=B.make_sup(bytes(body),code_off+text.functions['sup_entry'],'QST1',min_svc=6,
                     flags=B.SL_F_CACHED_OK,name='QS Touch test')
    state_off=(len(probe)+63)&~63
    struct.pack_into('<4I',body,0,0x31545351,state_off,ui_off,len(ui))
    data=B.make_sup(bytes(body),code_off+text.functions['sup_entry'],'QST1',min_svc=6,
                    flags=B.SL_F_CACHED_OK,name='QS Touch test',block_size=state_off+4096)
    assert len(data)==len(probe) and state_off>=len(data)
    return data,dict(code_off=code_off,code_bytes=len(text.code),ui_off=ui_off,ui_bytes=len(ui),
                     state_off=state_off,state_capacity=4096,ui=ui_info,
                     functions={k:code_off+v for k,v in text.functions.items()})


def build(out,card=False,debug=False):
    out=Path(out)
    if out.exists():raise ValueError('Use a new output directory')
    sup,facts=sup_file()
    out.mkdir(parents=True,exist_ok=False)
    files={'fpSup/QSTOUCH.BIN':sup}
    if card:
        ar,loader,_=B.boot_card(ui=True,slim=True)
        files.update({'AutoRun.txt':ar,'fpSup/LOADER.BIN':loader,'fpSup/SUPMGR.BIN':B.supmgr_sup()})
        for name,blob in B.ui_files().items():files['fpSup/UI/'+name]=blob
        if debug:files['fpSup/SHELL.BIN']=B.shell_sup()
    elif debug:raise ValueError('--debug requires --card')
    for name,data in files.items():
        p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    sources=[HERE/'build.py',HERE/'page.py',HERE/'touch_sup.c',
             *[HERE.parent/'core'/n for n in ('qs_tiles.c','qs_tiles.h','qs_tiles_touch.c','qs_tiles_touch.h')],
             HERE.parent/'native/build_tiles.py',ROOT/'projects/open-gate/build/res-qs/qs_page.py',
             ROOT/'research/ui/tools/native_ui_audit.py',ROOT/'research/ui/tools/arm_text/elf_text.py',
             ROOT/'fpSup/lossless/menu/build_menu_candidate.py',
             ROOT/'fpSup/fpsup-ui/fpsup_ui.c',ROOT/'fpSup/loader-v4/build_v4.py',ROOT/'fpSup/loader-v4/sloader4.h',
             *[ROOT/'fpSup/uishare/tab'/n for n in ('build_fp4.py','build_ft6.py','home4_page.py','manage_page.py','ft6_page.py')]]
    if card:
        sources += [ROOT/'fpSup/loader-v4'/n for n in ('sloader4.c','sloader4_entry.S','supmgr.c','fpsup_home.c')]
        sources += [ROOT/'fpSup/fp_usb_shell/v3/build_v3.py',ROOT/'fpSup/fp_usb_shell/build_autorun.py']
        sources += [ROOT/'fpSup/fp_usb_shell/asm'/n for n in ('loader.S','stage2.S','entries.S')]
    info=dict(product='Native QS Touch SUP, UI experiment',format='FSB4',loader_services=6,
              card=card,debug=debug,animation=False,camera_settings_connected=False,
              firmware_sha256=FIRMWARE_SHA256,
              on_camera_verified=False,physical_card_written=False,**facts,
              files={n:dict(bytes=len(d),sha256=hashlib.sha256(d).hexdigest()) for n,d in files.items()},
              source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (out/'build.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    return info


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--card',action='store_true')
    ap.add_argument('--debug',action='store_true')
    a=ap.parse_args();i=build(a.out,a.card,a.debug)
    print(json.dumps({'output':str(a.out.resolve()),'files':i['files']},indent=2))
