"""Offline frame-equality/contact evidence; not a generic mosaic detector."""
import json,pathlib,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw
import rawpy

HERE=pathlib.Path(__file__).resolve().parent
for label in sys.argv[1:]:
    dest=HERE/label
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(dest/'hdmi.mkv'),
        '-f','rawvideo','-pix_fmt','rgb24','-fps_mode','passthrough','pipe:1'])
    frames=np.frombuffer(raw,np.uint8).reshape((-1,576,1024,3))
    assert len(frames)==300
    starts=[0]
    for i in range(1,len(frames)):
        if not np.array_equal(frames[i,45:520,90:934],frames[i-1,45:520,90:934]):
            starts.append(i)
    spans=[(a,b-1,b-a) for a,b in zip(starts,starts[1:]+[len(frames)])]
    (dest/'scene-motion.json').write_text(json.dumps({'roi':[90,45,934,520],
        'frames':len(frames),'identical_runs':sorted(spans,key=lambda x:x[2],reverse=True)[:10],
        'limitation':'frame equality, not physical sensor cadence or a no-mosaic verdict'},indent=2)+'\n')
    selected=[i for i in starts if 22<=i<=115]
    sheet=Image.new('RGB',(4*384,((len(selected)+3)//4)*240),'#202020')
    draw=ImageDraw.Draw(sheet)
    for n,i in enumerate(selected):
        x=(n%4)*384;y=(n//4)*240
        sheet.paste(Image.fromarray(frames[i]).resize((384,216)),(x,y))
        draw.text((x+5,y+218),str(i),fill='white')
    sheet.save(dest/'unique-transition-contact.jpg')
    report=[]
    for f in sorted(dest.glob('*.DNG')):
        with rawpy.imread(str(f)) as r:
            a=r.raw_image.copy()
            rgb=r.postprocess(use_camera_wb=True,no_auto_bright=False)
            Image.fromarray(rgb).save(f.with_suffix('.png'))
            report.append({'file':f.name,'raw_shape':list(a.shape),
                'raw_min':int(a.min()),'raw_max':int(a.max()),'decoded_shape':list(rgb.shape)})
    if report:(dest/'raw-decode.json').write_text(json.dumps(report,indent=2)+'\n')
    print(label,sorted(spans,key=lambda x:x[2],reverse=True)[:3],flush=True)
