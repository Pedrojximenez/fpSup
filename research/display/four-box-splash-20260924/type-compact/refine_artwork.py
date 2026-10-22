from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import base64,zlib,shutil
root=Path(__file__).resolve().parent.parent
rev=Path(__file__).resolve().parent
repo=root.parent.parent
for rel in ['fpSup/fp_usb_shell/boot_splash.py','research/display/notes/BOOT_BANNER.md']:
 p=rev/'before'/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/rel,p)
font=ImageFont.truetype('/System/Library/Fonts/HelveticaNeue.ttc',160,index=3)
layers=[]
for text in ('fp','Sup'):
 mask=Image.new('L',(640,240));ImageDraw.Draw(mask).text((20,0),text,font=font,fill=255);layers.append(mask)
bounds=[m.getbbox() for m in layers];top=min(b[1] for b in bounds);bottom=max(b[3] for b in bounds)
masks=[]
for i,(m,b) in enumerate(zip(layers,bounds)):
 c=m.crop((b[0],top,b[2],bottom));w=round(c.width*36/c.height)
 c=c.resize((w,36),Image.Resampling.LANCZOS)
 visible=c.point(lambda a:255 if a>=9 else 0).getbbox()
 c=c.crop((visible[0],0,visible[2],36))
 if i==0:
  spaced=Image.new('L',(c.width+1,36));spaced.paste(c,(0,0));c=spaced
 masks.append(c)
p=rev/'before/fpSup/fp_usb_shell/boot_splash.py';s=p.read_text()
a=s.index('MASK_HEIGHT =');b=s.index('\n\ndef asset():',a)
replacement='''# Helvetica Neue Bold Italic, rendered on the host with a shared baseline.
# Masks are cropped to their 4-bit-alpha ink bounds; fp includes a 1px separator.
MASK_HEIGHT = 36
'''
for name,m in zip(('FP','SUP'),masks):
 encoded=base64.b85encode(zlib.compress(m.tobytes(),9)).decode()
 replacement+=f'{name}_WIDTH = {m.width}\n{name}_MASK = (\n'
 for k in range(0,len(encoded),88):replacement+='    '+repr(encoded[k:k+88])+'\n'
 replacement+=')\n'
s=s[:a]+replacement+s[b:]
s=s.replace('    box_size, gap = 24, 10\n    total = logo_width + 30', '    box_size, gap, logo_gap = 24, 10, 10\n    total = logo_width + logo_gap')
s=s.replace('    boxes_x = left + logo_width + 30','    boxes_x = left + logo_width + logo_gap')
p=rev/'staging/fpSup/fp_usb_shell/boot_splash.py';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
(root/'staging/fpSup/fp_usb_shell/boot_splash.py').write_text(s)
print('Helvetica Neue Bold Italic masks:', [(m.width,m.height) for m in masks])
