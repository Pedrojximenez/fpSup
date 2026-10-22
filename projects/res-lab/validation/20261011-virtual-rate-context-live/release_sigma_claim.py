"""One fresh exact SIGMA interface claimant release; no retry/kill loop."""
import fcntl
import json
import os
import plistlib
import re
import subprocess
import sys
import time
import camera as C

label=sys.argv[1]
assert re.fullmatch(r'[a-z0-9-]+',label)
dest=C.HERE/('usb-'+label+'.json')
assert not dest.exists()
raw=subprocess.check_output(['ioreg','-a','-l','-p','IOService'])
owners=[]
def walk(node,camera=False):
    if isinstance(node,dict):
        camera=camera or (node.get('USB Product Name')=='SIGMA fp' and node.get('IOObjectClass')=='IOUSBHostDevice')
        if camera and node.get('bInterfaceNumber')==0 and node.get('UsbExclusiveOwner'):
            owners.append(node['UsbExclusiveOwner'])
        for child in node.get('IORegistryEntryChildren',[]): walk(child,camera)
    elif isinstance(node,list):
        for child in node: walk(child,camera)
walk(plistlib.loads(raw))
assert len(owners)<=1,owners
report={'owners':owners,'released':[]}
dest.write_text(json.dumps(report,indent=2)+'\n')
print(report,flush=True)
with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for owner in owners:
        own=re.fullmatch(r'pid (\d+), fpshd',owner)
        if own:
            pid=int(own[1])
            assert pid==int((C.HERE/'daemon-pid.txt').read_text()),owner
            command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()
            assert command==str(C.live.SHELL/'fpshd'),command
            report['verified_own_daemon_reused']=pid
            dest.write_text(json.dumps(report,indent=2)+'\n')
            continue
        match=re.fullmatch(r'pid (\d+), ptpcamerad',owner)
        assert match,owner
        pid=int(match[1])
        command=subprocess.check_output(['ps','-p',str(pid),'-o','comm='],text=True).strip()
        assert command=='/usr/libexec/ptpcamerad',command
        os.kill(pid,15)
        for _ in range(25):
            if subprocess.run(['ps','-p',str(pid),'-o','comm='],capture_output=True,text=True).stdout.strip()!=command:
                break
            time.sleep(.01)
        else:
            os.kill(pid,9)
            # SIGKILL is asynchronous: wait for this exact process to leave
            # before claiming its interface, without stopping another PID.
            for _ in range(25):
                if subprocess.run(['ps','-p',str(pid),'-o','comm='],capture_output=True,text=True).stdout.strip()!=command:
                    break
                time.sleep(.01)
            else:
                raise RuntimeError('Exact claimant did not exit; no further release')
        report['released'].append(pid)
        dest.write_text(json.dumps(report,indent=2)+'\n')
    # Acquire through the existing verified daemon immediately after release.
    report['native_rec_reply']=C.live.checked_sh('status get is_recording')
    dest.write_text(json.dumps(report,indent=2)+'\n')
    print(report,flush=True)
