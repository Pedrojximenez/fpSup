import sys, pathlib, subprocess, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3] / 'projects/gyro-sup'))
from build_stage5_autorun import extract_and_relocate, words
HERE=pathlib.Path(__file__).resolve().parent
TRAMP=0xC072F400; RESULT=0xC072F480; SITE=0xC030D148; ORIG=0xEB0022B0
with tempfile.TemporaryDirectory() as d:
    o=pathlib.Path(d)/'f.o'
    r=subprocess.run(['clang','-target','armv7-none-eabi','-c',str(HERE/'frameexpos_capture.S'),'-o',str(o)],capture_output=True,text=True)
    if r.returncode: sys.stderr.write(r.stderr); sys.exit(1)
    w=words(extract_and_relocate(o))
end=TRAMP+len(w)*4
assert end<=RESULT, f"blob overruns RESULT 0x{end:08X}"
patch=0xEB000000|(((TRAMP-(SITE+8))>>2)&0xFFFFFF)
print(f"# frameexpos capture hook: {len(w)}w @0x{TRAMP:08X}..0x{end:08X}, result@0x{RESULT:08X}")
for i,x in enumerate(w): print(f"mem set 0x{TRAMP+i*4:08X} 0x{x:08X}")
print(f"# patch BL FrameExpos 0x{SITE:08X}: 0x{ORIG:08X} -> 0x{patch:08X}")
print(f"mem set 0x{SITE:08X} 0x{patch:08X}")
