"""Native LCD evidence when the user has physically disconnected HDMI.

Use the released consumer's fixed-address busy predicates before file tools.
REC=0 alone is insufficient: movie writer and XMP ownership must also be idle.
The caller holds the AF lease. No screenshot or key is replayed.
"""
import hashlib
import importlib
import pathlib
import shutil
import numpy as np
from PIL import Image
import camera as C


def idle():
    pf=C.live.putfile
    assert C.recording()==0
    selector=pf.mem_get(0xC347D1D4,tries=1)[0]
    at=0xC3476609 if selector==0x21 else 0xC347E08F
    word=pf.mem_get(at&~3,tries=1)[0]
    recording=(word>>((at&3)*8))&255
    xmp=pf.mem_get(0xC358E140,tries=1)[0]
    writing=pf.mem_get(0xC35A952C,tries=1)[0]&255
    result={'native_rec':0,'selector':selector,'movie_recording':recording,
            'xmp_file_pointer':xmp,'movie_writing':writing}
    assert pf.mem_get(0xC347D1D4,tries=1)==[selector]
    assert C.recording()==0
    assert recording==xmp==writing==0,result
    return result


def shot(tag,dest):
    before_idle=idle()
    assert C.live.screen()=='LV_CINE_MEDIUM'
    source=pathlib.Path(C.live.__file__).with_name('screenshots')
    before=set(source.glob('*.jpg'))
    getter=importlib.import_module('getfile')
    getter.read_direct=lambda addr,size:C.live.putfile.read_bulk(addr,size,'tagged')
    C.live.shot(tag)
    new=set(source.glob('*.jpg'))-before
    assert len(new)==1,new
    original=new.pop();assert original.name.endswith('-'+tag+'.jpg')
    target=dest/(tag+'.jpg');assert not target.exists()
    shutil.copy2(original,target)
    im=np.asarray(Image.open(target).convert('RGB'))
    h,w=im.shape[:2]
    rgb=im[:min(50,h//10),int(w*.42):int(w*.60)].astype(np.int16)
    green=(rgb[:,:,1]>110)&(rgb[:,:,0]<100)&(rgb[:,:,2]<100)
    red=(rgb[:,:,0]>110)&(rgb[:,:,1]<100)&(rgb[:,:,2]<100)
    result={'source':'native_LCD','path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'standby_pixels':int(green.sum()),'rec_pixels':int(red.sum()),
            'standby_visible':bool(green.sum()>10 and red.sum()<=10),'idle_before':before_idle,
            'idle_after':idle()}
    assert result['standby_visible'],result
    return result
