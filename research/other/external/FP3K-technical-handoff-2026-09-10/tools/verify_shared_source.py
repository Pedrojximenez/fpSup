"""Run from archive root; clang and upstream armasm.py required. No media access."""
from pathlib import Path
import argparse,hashlib,struct,sys,os
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--assembler-dir',type=Path,default=ROOT/'research/fpSup/fp_usb_shell');args=p.parse_args()
if not (args.assembler_dir/'armasm.py').is_file():raise SystemExit('Obtain upstream fpSup at research/fpSup, or pass --assembler-dir pointing to its fp_usb_shell directory.')
sys.path.insert(0,str(args.assembler_dir.resolve()))
from armasm import assemble,symbols
os.chdir(ROOT)
src=ROOT/'tools/fp3k_native_menu.S';code=bytearray(assemble(src));syms=symbols(src)
struct.pack_into('<I',code,syms['checksum_word'],(-sum(struct.unpack('<'+'I'*(len(code)//4),code)))&0xffffffff)
report=[]
for name,data in [('FP3KMENU.BIN',bytes(code)),('loader.bin',assemble(ROOT/'tools/fp3k_menu_boot.S'))]:
 expected=(ROOT/'prototype/fp3k-0.3.5-fullheight'/name).read_bytes()
 if data!=expected:raise SystemExit('SOURCE MISMATCH: '+name)
 print(name,len(data),hashlib.sha256(data).hexdigest(),'EXACT MATCH')
print('Source/loader consistency verified; this is not a hardware regression test.')
