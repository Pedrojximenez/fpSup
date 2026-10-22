from pathlib import Path
import shutil
rev=Path(__file__).resolve().parent
repo=rev.parent.parent.parent
files=['fpSup/fp_usb_shell/boot_splash.py','fpSup/fp_usb_shell/test_splash.py','fpSup/fp_usb_shell/build_autorun.py','fpSup/fp_usb_shell/README.md','research/display/notes/BOOT_BANNER.md']
for rel in files:
 assert (repo/rel).read_bytes()==(rev/'before'/rel).read_bytes(),f'Changed concurrently: {rel}'
for rel in files:
 shutil.copy2(rev/'staging'/rel,repo/rel)
 print(rel)
