import fcntl,json,sys
from common import *
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 pf=live.putfile
 out={'idle':B.idle(),'screen':live.screen(),'slot':live.checked_sh('sdcard slot').strip(),
  'fpSup':B.entries(live.checked_sh('dir \\fpSup')),
  'C038C77C':hex(pf.mem_get(0xC038C77C,tries=1)[0]),
  'lossless':live.checked_sh('gui geti MV_fpLossless').strip(),
  'framerate':live.checked_sh('menu SetMovFramerate').strip()}
 print(json.dumps(out,indent=1))
