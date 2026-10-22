"""Copy only reviewed offline source/docs after verifying every before-image."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parent
repo=root.parents[2]
files=[
 'fpSup/fp_usb_shell/build_autorun.py',
 'fpSup/fp_usb_shell/boot_splash.py',
 'fpSup/fp_usb_shell/templates/stage2.S',
 'fpSup/fp_usb_shell/templates/splash_finish.S',
 'fpSup/fp_usb_shell/test_splash.py',
 'fpSup/fp_usb_shell/README.md',
 'research/display/notes/BOOT_BANNER.md',
 'projects/usb-shell-sup/notes/CARD_BUILD_PIPELINE.md',
]
for rel in files:
 dst=repo/rel
 old=root/'original'/(rel.removeprefix('fpSup/') if rel.startswith('fpSup/') else rel)
 src=root/'staging'/rel
 assert src.is_file(),src
 if old.exists():
  assert dst.read_bytes()==old.read_bytes(),f'Changed concurrently; not writing: {dst}'
 else:
  assert not dst.exists(),f'New path appeared concurrently; not writing: {dst}'
for rel in files:
 shutil.copy2(root/'staging'/rel,repo/rel)
 print(rel)
