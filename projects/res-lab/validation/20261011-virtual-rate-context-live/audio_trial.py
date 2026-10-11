"""One ordinary audio-off contrast, restoring only after verified idle/STBY."""
import fcntl,json,pathlib,subprocess,sys
import numpy as np
from PIL import Image
import camera as C
sys.path.insert(0,str(C.HERE))
import record_trial as R
proof={'phase':'preflight','original_audio':None}
path=C.HERE/'audio-comparison.json';assert not path.exists()
def save():path.write_text(json.dumps(proof,indent=2)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert C.recording()==0 and C.live.screen()=='LV_CINE_MEDIUM'
 original=C.live.checked_sh('menu SetAudioRecSupport').strip();assert original=='1'
 proof['original_audio']=original;save()
 C.live.checked_sh('menu SetAudioRecSupport 0')
 assert C.live.checked_sh('menu SetAudioRecSupport').strip()=='0'
 proof['phase']='audio_off_verified';save()
try:
 sys.argv=['record_trial.py','tagged-280-audiooff', '27972','0','quiet'];R.main()
finally:
 with open('/tmp/fp-af-fusion.lock') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert C.recording()==0
  image=C.HERE/'before-audio-restore.png';assert not image.exists()
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','avfoundation','-framerate','30','-pixel_format','uyvy422','-i','AVerMedia ExtremeCap UVC:none','-vf','scale=1024:576','-frames:v','1',str(image)],check=True,timeout=15)
  assert R.overlay(np.asarray(Image.open(image).convert('RGB')))['standby_visible']
  assert C.recording()==0
  C.live.checked_sh('menu SetAudioRecSupport '+original)
  assert C.live.checked_sh('menu SetAudioRecSupport').strip()==original
  proof['phase']='restored_verified';save()
