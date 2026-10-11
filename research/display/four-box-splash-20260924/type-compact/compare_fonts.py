from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
out=Path(__file__).resolve().parent
fonts=[('Helvetica Neue Bold Italic','/System/Library/Fonts/HelveticaNeue.ttc',3),('Helvetica Neue Condensed Bold','/System/Library/Fonts/HelveticaNeue.ttc',4),('DIN Alternate Bold','/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf',0),('Futura Bold','/System/Library/Fonts/Supplemental/Futura.ttc',2)]
canvas=Image.new('RGB',(1024,360),'#424648');cd=ImageDraw.Draw(canvas)
for i,(name,path,index) in enumerate(fonts):
 f=ImageFont.truetype(path,160,index=index)
 masks=[]
 for text in ('fp','Sup'):
  mask=Image.new('L',(640,240));ImageDraw.Draw(mask).text((20,0),text,font=f,fill=255)
  masks.append(mask)
 boxes=[m.getbbox() for m in masks];top=min(b[1] for b in boxes);bottom=max(b[3] for b in boxes)
 size=36
 layers=[]
 for m,b in zip(masks,boxes):
  c=m.crop((b[0],top,b[2],bottom));w=round(c.width*size/c.height)
  layers.append(c.resize((w,size),Image.Resampling.LANCZOS))
 w=sum(m.width for m in layers)+1;left=(1024-(w+10+126))//2;y=i*90+20
 for mask,col in zip(layers,('#FFFFFF','#DD3355')):
  canvas.paste(col,(left,y),mask);left+=mask.width+1
 bx=left+9
 for n in range(4):
  x=bx+n*34;cy=y+(36-24)//2
  cd.rectangle((x,cy,x+23,cy+23),outline='#888888',width=2)
  if n<2:cd.rectangle((x+5,cy+5,x+18,cy+18),fill='#EEEEEE')
 cd.text((24,i*90+63),name,fill='#FFFFFF')
canvas.save(out/'font-options.png')
