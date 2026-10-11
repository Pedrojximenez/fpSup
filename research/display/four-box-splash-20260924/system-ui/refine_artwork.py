from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import base64,zlib,shutil
rev=Path(__file__).resolve().parent;root=rev.parent;repo=root.parent.parent
for rel in ['fpSup/fp_usb_shell/boot_splash.py','research/display/notes/BOOT_BANNER.md']:
 p=rev/'before'/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/rel,p)
font=ImageFont.truetype('/System/Library/Fonts/SFNS.ttf',128)
font.set_variation_by_axes([100,28,400,400])
# Render on one baseline with the font's natural spacing at the color boundary.
fullbox=font.getbbox('fpSup');leftpad=20
layers=[]
for text,x in [('fp',leftpad),('Sup',leftpad+font.getlength('fp'))]:
 m=Image.new('L',(640,240));ImageDraw.Draw(m).text((x,0),text,font=font,fill=255);layers.append(m)
bounds=[m.getbbox() for m in layers];left=min(b[0] for b in bounds);right=max(b[2] for b in bounds);top=min(b[1] for b in bounds);bottom=max(b[3] for b in bounds)
scale=28/(bottom-top);width=round((right-left)*scale)
resized=[m.crop((left,top,right,bottom)).resize((width,28),Image.Resampling.LANCZOS) for m in layers]
# The upright glyphs do not overlap; split at the first visible Sup pixel and
# preserve the original spacing inside the fp mask instead of trimming it away.
sup_start=resized[1].point(lambda a:255 if a>=9 else 0).getbbox()[0]
masks=[resized[0].crop((0,0,sup_start,28)),resized[1].crop((sup_start,0,width,28))]
s=(rev/'before/fpSup/fp_usb_shell/boot_splash.py').read_text()
a=s.index('# Helvetica Neue Bold Italic');b=s.index('\n\ndef asset():',a)
replacement='''# SF system UI, regular upright weight, with the font's natural baseline/spacing.
# Only these rendered alpha masks are carried; no font is needed by the builder.
MASK_HEIGHT = 28
'''
for name,m in zip(('FP','SUP'),masks):
 e=base64.b85encode(zlib.compress(m.tobytes(),9)).decode();replacement+=f'{name}_WIDTH = {m.width}\n{name}_MASK = (\n'
 for k in range(0,len(e),88):replacement+='    '+repr(e[k:k+88])+'\n'
 replacement+=')\n'
s=s[:a]+replacement+s[b:]
s=s.replace('box_size, gap, logo_gap = 24, 10, 10','box_size, gap, logo_gap = 12, 4, 8')
s=s.replace('# Crisp small squares: 2px outline, a 3px breathing space before fill.', '# Quiet UI indicators: 1px outline and a 1px gap before the fill.')
s=s.replace('border = x < 2 or x >= box_size-2 or y < 2 or y >= box_size-2', 'border = x == 0 or x == box_size-1 or y == 0 or y == box_size-1')
s=s.replace('inside = 5 <= x < box_size-5 and 5 <= y < box_size-5', 'inside = 2 <= x < box_size-2 and 2 <= y < box_size-2')
s=s.replace('0xF666 if border else 0xFEEE','0xF888 if border else 0xFEEE')
s=s.replace('WHITE, PINK, OUTLINE, FILL = 0xFFFFFF, 0xDD3355, 0x666666, 0xEEEEEE','WHITE, PINK, OUTLINE, FILL = 0xFFFFFF, 0xDD3355, 0x888888, 0xEEEEEE')
p=rev/'staging/fpSup/fp_usb_shell/boot_splash.py';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
(root/'staging/fpSup/fp_usb_shell/boot_splash.py').write_text(s)
print('Regular system UI alpha masks:',[(m.width,m.height) for m in masks])
