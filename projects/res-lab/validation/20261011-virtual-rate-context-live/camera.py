"""Task-scoped native UI and bounded owner reads; no private picker calls."""
import fcntl
import hashlib
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REFERENCE = pathlib.Path(os.environ.get('RESLAB_LIVE_CARD',str(HERE/'reference')))
os.environ['RESLAB_LIVE_CARD'] = str(REFERENCE)
sys.path.insert(0, str(HERE.parent/'20261009-oncamera'))
import live_camera as live
live.LOG = HERE/'commands.jsonl'
# Shared development sources can change independently of the resident v17.
# Load its preserved field layout before helpers add their build search paths.
sys.path.insert(0, str(HERE/'reference-source-v17'))
import ogc_layout
assert hashlib.sha256(pathlib.Path(ogc_layout.__file__).read_bytes()).hexdigest() == \
    json.loads((HERE/'reference-source-v17/provenance.json').read_text())['sha256']
import fps_state
import inspect_runtime as inspect
from ogc_layout import S


def value(name):
    reply = live.checked_sh('gui geti '+name)
    match = re.fullmatch(r'\s*OK:'+name+r' -> (-?\d+)\s*', reply)
    assert match, reply
    return int(match[1])


def recording():
    reply = live.checked_sh('status get is_recording')
    match = re.fullmatch(r'\s*is_recording -> ([01])\s*', reply)
    assert match, reply
    return int(match[1])


def key(name):
    assert name in ('UP','DOWN','LEFT','RIGHT','OK','MENU','QS','DISP','AEL','Fn')
    live.checked_sh('key '+name+'ON')
    time.sleep(.8 if name == 'MENU' else .12)
    live.checked_sh('key '+name+'OFF')
    time.sleep(.65)


def snapshot():
    assert recording() == 0
    r = fps_state.snapshot()
    s = int(r['consumer_state'],16)
    r['rate_notification'] = {k:live.putfile.mem_get(s+S[k])[0]
                              for k in ('RATE_LVOWED','RATE_LV_RELOADS')}
    # Candidate's immutable core before state, skipping the saved CFG record.
    core = int(r['consumer_base'],16)
    raw = (REFERENCE/'fpSup/32RESCUS.BIN').read_bytes()
    start, end = 128, 128+inspect.FACT['rescustom']['text']
    assert start < end < len(raw)
    got = live.putfile.read_bulk(core+start,end-start,'tagged')
    assert got == raw[start:end], 'loaded core differs from candidate'
    r['loaded_core_sha256'] = hashlib.sha256(got).hexdigest()
    # Verify both replaced native commit shims against their exact built bytes.
    cf = inspect.FACT['rescustom']
    image = raw[cf['img_off']:]
    r['rate_shims'] = []
    sites = [(0xc057a6f8,116),(0xc05821b8,116),(0xc00c9bd0,80)]
    if 'HDR_COPY_HITS' in cf['S']:
        sites += [(0xc00fbb90,104),(0xc03a5144,60)]
    for site,length in sites:
        hook = next(h for h in cf['hooks'] if int(h['site'],16)==site)
        thumb = hook['kind']==2
        if thumb:
            veneer = inspect.thumb_b(site)
        else:
            # Function-entry hooks branch; call-site hooks preserve native LR
            # with BL. Validate the exact kind before decoding either offset.
            w = live.putfile.mem_get(site,tries=1)[0]
            assert w & 0xff000000 == (0xeb000000 if hook['kind']==1 else 0xea000000), (hex(site),hex(w),hook)
            d = (w & 0xffffff) << 2
            if d & 0x2000000:
                d -= 0x4000000
            veneer = (site+8+d)&0xffffffff
        assert 0xc072e064 <= veneer <= 0xc072efb4-8
        words = live.putfile.mem_get(veneer,2)
        assert words[0] == (0xf000f8df if thumb else 0xe51ff004), (hex(site),words)
        actual = words[1]
        relative = int(hook['to'],16)-0xc0730000
        assert actual == core+cf['img_off']+relative
        expected = image[relative:relative+length]
        got = live.putfile.read_bulk(actual,len(expected),'tagged')
        assert got == expected, (hex(site),hex(actual))
        r['rate_shims'].append({'site':hex(site),'target':hex(actual),
                                'sha256':hashlib.sha256(got).hexdigest()})
    if 'HDR_COPY_HITS' in cf['S']:
        r['header_copy'] = {k:live.putfile.mem_get(s+cf['S'][k],tries=1)[0]
            for k in ('HDR_COPY_CALLS','HDR_COPY_HITS','HDR_COPY_SRC','HDR_COPY_DST',
                      'HDR_COPY_BYTES','HDR_COPY_WHY','HDR_COPY_FRAME','BULK_HITS','BULK_LAST')}
    if 'M12_LEGACY_HITS' in cf['S']:
        r['sensorlab_profile'] = {k:live.putfile.mem_get(s+cf['S'][k],tries=1)[0]
            for k in ('M12_LEGACY_HITS','M12_LEGACY_PID')}
    return r


def main():
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        action = sys.argv[1]
        if action == 'state':
            print(live.screen(), flush=True)
            for name in sys.argv[2:]:
                print(name,value(name),flush=True)
        elif action == 'key':
            assert recording() == 0
            for name in sys.argv[2:]:
                key(name)
                print(name,live.screen(),flush=True)
        elif action == 'shell':
            assert recording() == 0
            for cmd in sys.argv[2:]:
                print(cmd+'\n'+live.checked_sh(cmd),flush=True)
        elif action == 'fps':
            assert recording() == 0
            assert live.screen() == 'B2_5' and value('MENU_Level2') == 4434
            target = int(sys.argv[2])
            assert target in (2,3,8,9,10)
            key('RIGHT')
            current = value('B2_n5_ListFocus4')
            assert 0 <= current <= 12
            for _ in range(13):
                if current == target:
                    break
                wanted = current+(1 if current < target else -1)
                key('DOWN' if current < target else 'UP')
                current = value('B2_n5_ListFocus4')
                assert current == wanted
            assert current == target
            key('OK')
            assert value('MV_FrameRate') == target
            print('Committed FPS row',target,flush=True)
        elif action == 'snapshot':
            dest = HERE/(sys.argv[2]+'.json')
            assert not dest.exists()
            r = snapshot()
            dest.write_text(json.dumps(r,indent=2)+'\n')
            print(json.dumps({k:r[k] for k in ('screen','consumer','producer',
                'fps_state','engine_fps','sensor_timing_fps','rate_notification') if k in r},indent=2),flush=True)
        elif action == 'reboot':
            owned = int(sys.argv[2])
            exe = str(live.SHELL/'fpshd')
            assert subprocess.check_output(['ps','-p',str(owned),'-o','command='],text=True).strip() == exe
            assert recording() == 0
            try:
                print('Single reboot:',live.checked_sh('reboot'),flush=True)
            except RuntimeError as exc:
                print(str(exc),flush=True)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect('/tmp/fpshd.sock')
                sock.sendall(b'QUIT\n')
                reply = sock.recv(1024).decode().strip()
                assert reply == 'OK bye',reply
            time.sleep(25)
            with (HERE/'daemon.log').open('ab') as log:
                p = subprocess.Popen([exe],cwd=live.SHELL,stdout=log,stderr=log,start_new_session=True)
            (HERE/'daemon-pid.txt').write_text(str(p.pid)+'\n')
            print('Replacement daemon:',p.pid,flush=True)
            time.sleep(2)
            assert p.poll() is None
            print('Postboot recording:',recording(),flush=True)
        else:
            raise ValueError(action)


if __name__ == '__main__':
    main()
