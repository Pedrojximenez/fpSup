"""One reversible native data-literal experiment, no hook/code/pool replacement.

C03A5050 loads C0B9E5D8 as actual FS bulk limit (offline native test included).
Test whether a batch smaller than one actual DNG restores early completion.
The callback, 256 KiB work buffer, descriptor depth and all source remain intact.
The single RAM word is restored only after fresh REC=0 and positive HDMI STBY.
"""
import fcntl,json,pathlib,subprocess,sys
import numpy as np
from PIL import Image
import camera as C
sys.path.insert(0,str(C.HERE))
import record_trial as R
LITERAL=0xc0b9e5d8;OLD=0x4000000;NEW=0x100000
LABEL=sys.argv[1] if len(sys.argv)>1 else 'tagged-280-bulk1-quiet'
assert LABEL.startswith('tagged-280-bulk1-') and all(c.islower() or c.isdigit() or c=='-' for c in LABEL)
REPORT=C.HERE/(LABEL+'-mutation.json')
assert not REPORT.exists()
proof={'site':hex(LITERAL),'old':hex(OLD),'temporary':hex(NEW),'phase':'not_written','card_files_changed':False}
def save():REPORT.write_text(json.dumps(proof,indent=2)+'\n')
original=C.snapshot
armed=False

def preflight():
 global armed
 r=original()
 if not armed:
  assert r['screen']=='LV_CINE_MEDIUM' and C.recording()==0
  assert r['producer']['applied_geometry']==12 and r['producer']['applied_valid']==1
  assert [r['producer'][k] for k in ('out_w','out_h','bin_h','bin_v','crop_w','crop_h','lens_on','output_policy')]==[992,662,1,1,0,0,0,0]
  assert r['fps_state']['VRATE']==27972 and r['picked_entry']['VRATE']==27972
  assert r['quality_getter'].strip()=='0'
  expected=[OLD,0,0x40000,0xc03a55d0]
  assert C.live.putfile.mem_get(LITERAL,4,tries=1)==expected
  proof.update(phase='writing',runtime=r);save();armed=True
  C.live.putfile.mem_set(LITERAL,NEW)
  assert C.live.putfile.mem_get(LITERAL,4,tries=1)==[NEW,*expected[1:]]
  proof['phase']='verified_temporary';save()
 return r
C.snapshot=preflight
sys.argv=['record_trial.py',LABEL,'27972','0','quiet']
try:
 R.main()
finally:
 if armed:
  with open('/tmp/fp-af-fusion.lock') as lease:
   fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
   assert C.recording()==0,'No restore until native standby'
   shot=C.HERE/(LABEL+'-before-restore.png');assert not shot.exists()
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','avfoundation','-framerate','30','-pixel_format','uyvy422','-i','AVerMedia ExtremeCap UVC:none','-vf','scale=1024:576','-frames:v','1',str(shot)],check=True,timeout=15)
   assert R.overlay(np.asarray(Image.open(shot).convert('RGB')))['standby_visible'],'No restore until HDMI standby'
   got=C.live.putfile.mem_get(LITERAL,4,tries=1)
   assert got[0] in (OLD,NEW) and got[1:]==[0,0x40000,0xc03a55d0]
   C.live.putfile.mem_set(LITERAL,OLD)
   assert C.live.putfile.mem_get(LITERAL,4,tries=1)==[OLD,0,0x40000,0xc03a55d0]
   proof.update(phase='restored_verified',standby_proof=str(shot));save()
