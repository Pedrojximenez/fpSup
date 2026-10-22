#!/usr/bin/env python3
from pathlib import Path
import struct, subprocess, tempfile
from build_false_color_counter_probe import extract_text, branch, words

LOAD=0xC072DE64
STATE=0xC072E500
HOOKS=[
    (0xC005DBA0,0xE92D4070,0x000),
    (0xC0528700,0xE92D4BF0,0x080),
    (0xC05276F0,0xE92D40F0,0x100),
]

with tempfile.TemporaryDirectory() as td:
    obj=Path(td)/'p.o'
    subprocess.run(['clang','-target','armv7-none-eabi','-c','false_color_drawpath_probe.S','-o',str(obj)],check=True)
    code=extract_text(obj)
assert len(code) < STATE-LOAD
lines=[
 '# SIGMA fp 5.02 false-color activation/draw-path counter',
 '# 1 pulse=start; 2 pulses=armed; long pulse=saved and restored.',
]
for hook,orig,_ in HOOKS: lines.append(f'mem set {hook:#010x} {orig:#010x}')
lines += ['display monitor 0 1','display colorbar 1 0','ctrl sleep 700','display colorbar 0 0','ctrl sleep 400']
for i,w in enumerate(words(code)): lines.append(f'mem set {LOAD+4*i:#010x} {w:#010x}')
init=[0x32504346]+[0]*11+[0x00050202]
for i,w in enumerate(init): lines.append(f'mem set {STATE+4*i:#010x} {w:#010x}')
lines.append(f'mem save \\FCDCODE.BIN {LOAD:#010x},,{len(code):#x}')
for hook,_,off in HOOKS: lines.append(f'mem set {hook:#010x} {branch(hook,LOAD+off):#010x}')
lines += ['display colorbar 1 0','ctrl sleep 500','display colorbar 0 0','ctrl sleep 300','display colorbar 1 0','ctrl sleep 500','display colorbar 0 0',
          '# Toggle stock False Color OFF/ON and change its style once.','ctrl sleep 45000']
for hook,orig,_ in HOOKS: lines.append(f'mem set {hook:#010x} {orig:#010x}')
lines += ['ctrl sleep 200',f'mem save \\FCDPATH.BIN {STATE:#010x},,0x40','display colorbar 1 0','ctrl sleep 1200','display colorbar 0 0','']
Path('AutoRun_false_color_drawpath.txt').write_text('\n'.join(lines),encoding='ascii')
print('code_size',hex(len(code)))
for h,_,o in HOOKS: print(hex(h),hex(branch(h,LOAD+o)))
