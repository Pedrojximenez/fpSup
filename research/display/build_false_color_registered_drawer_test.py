#!/usr/bin/env python3
from pathlib import Path
import subprocess,tempfile
from build_false_color_counter_probe import extract_text,branch,words

LOAD=0xC072DE64; STATE=0xC072E500
CYCH=0xC05276F0; CYCORG=0xE92D40F0
SETH=0xC005DBA0; SETORG=0xE92D4070
OFF={'cyc':0x000,'setter':0x100,'draw':0x180,'destruct':0x280,'setup':0x290,'teardown':0x2a0,'noop':0x2b0,'true':0x2c0}
with tempfile.TemporaryDirectory() as td:
 o=Path(td)/'x.o'; subprocess.run(['clang','-target','armv7-none-eabi','-c','false_color_registered_drawer_test.S','-o',str(o)],check=True); code=extract_text(o)
assert len(code)<STATE-LOAD
L=['# SIGMA fp 5.02 registered XC_DrawInterface visible test','# 1=start, 2=armed. Toggle stock False Color ON to show top-left block. Long=unregistered/saved.',f'mem set {CYCH:#010x} {CYCORG:#010x}',f'mem set {SETH:#010x} {SETORG:#010x}','display monitor 0 1','display colorbar 1 0','ctrl sleep 700','display colorbar 0 0','ctrl sleep 400']
for i,w in enumerate(words(code)):L.append(f'mem set {LOAD+4*i:#010x} {w:#010x}')
# state then ABI vtable (offset-to-top, typeinfo, v0..v6) and object vptr
for i,w in enumerate([0x33504346,0,0,0,0,0,0,0,0x00050203]):L.append(f'mem set {STATE+4*i:#010x} {w:#010x}')
vt=[0,0,LOAD+OFF['destruct'],LOAD+OFF['draw'],LOAD+OFF['setup'],LOAD+OFF['teardown'],LOAD+OFF['noop'],LOAD+OFF['true'],LOAD+OFF['noop']]
for i,w in enumerate(vt):L.append(f'mem set {STATE+0x40+4*i:#010x} {w:#010x}')
L.append(f'mem set {STATE+0x80:#010x} {STATE+0x40:#010x}')
L += [f'mem set {SETH:#010x} {branch(SETH,LOAD+OFF["setter"]):#010x}',f'mem set {CYCH:#010x} {branch(CYCH,LOAD):#010x}','display colorbar 1 0','ctrl sleep 500','display colorbar 0 0','ctrl sleep 300','display colorbar 1 0','ctrl sleep 500','display colorbar 0 0','ctrl sleep 45000',f'mem set {STATE+8:#010x} 0x00000001','ctrl sleep 1000',f'mem set {CYCH:#010x} {CYCORG:#010x}',f'mem set {SETH:#010x} {SETORG:#010x}','ctrl sleep 200',f'mem save \\FCVIS.BIN {STATE:#010x},,0xc0','display colorbar 1 0','ctrl sleep 1200','display colorbar 0 0','']
Path('AutoRun_false_color_visible_test.txt').write_text('\n'.join(L),encoding='ascii')
print(hex(len(code)))
