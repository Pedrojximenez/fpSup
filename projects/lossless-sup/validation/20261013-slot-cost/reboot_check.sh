#!/bin/zsh
# Idle checks, shell reboot, wait for CINE, print the LOSS record and SD mode.
cd /Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell || exit 1
python3 -B -c "
import putfile as pf
assert pf.sh('status get is_recording',retries=0,timeout_ms=5000).strip()=='is_recording -> 0'
assert pf.mem_get(0xc358e140)[0]==0
try: print(pf.sh('reboot',retries=0,timeout_ms=5000))
except Exception as e: print('reboot reply', e)
"
for i in $(seq 1 30); do
  python3 -c "import time; time.sleep(3)"
  python3 -B -c "
import putfile as pf
print(pf.sh('status get app_current',retries=0,timeout_ms=3000).strip())
" 2>/dev/null | grep -q "app_current -> 2" && break
done
python3 -B -c "
import putfile as pf, sys
sys.path.insert(0,'../lossless'); import card_status as cs
r=cs.find_record(pf.mem_get); print('record', [hex(x) for x in r] if r else None)
print(pf.sh('sdcard sdmode').strip(), pf.sh('gui geti MV_fpLossless').strip(), pf.sh('gui geti MV_FrameRate').strip(), pf.sh('menu SetMovRecSize').strip())
"
