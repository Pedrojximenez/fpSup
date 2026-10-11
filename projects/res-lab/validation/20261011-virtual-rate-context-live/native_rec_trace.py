"""Task-scoped native recorder logs, read only after positive HDMI STBY.

Use the firmware's existing Logger commands and owned T_LOGGERMEMORY rings.
No new code, recorder hook, DMA buffer or raw descriptor pool is installed.
DEBUG logging changes scheduling, so these are diagnostic trials only.
"""
import fcntl
import hashlib
import json
import pathlib
import struct
import subprocess
import sys

import numpy as np
from PIL import Image
import camera as C

LOGGER = 0xC303448C
CATEGORIES = ((2, 'RECMGR'), (23, 'RECMGR2'))
CAPACITY = 4096


def idle(dest):
    assert C.recording() == 0
    image = dest / 'standby.png'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'avfoundation',
                    '-framerate', '30', '-pixel_format', 'uyvy422', '-i',
                    'AVerMedia ExtremeCap UVC:none', '-vf', 'scale=1024:576',
                    '-frames:v', '1', str(image)], check=True, timeout=15)
    roi = np.asarray(Image.open(image).convert('RGB'))[:40,440:650].astype(np.int16)
    assert ((roi[:,:,1]>110)&(roi[:,:,0]<85)&(roi[:,:,2]<85)).sum()>10
    assert ((roi[:,:,0]>110)&(roi[:,:,1]<85)&(roi[:,:,2]<85)).sum()<=10
    assert C.recording() == 0


def header(bit):
    ptr = C.live.putfile.mem_get(LOGGER + 0x20 + 4*bit, tries=1)[0]
    assert 0xC3000000 <= ptr < 0xC4000000 or 0x45000000 <= ptr < 0x60000000
    desc = C.live.putfile.mem_get(ptr, 8, tries=1)
    assert desc[7] in (0xC0727508, 0xC0727374), (hex(ptr), desc)
    assert desc[1] in (256, CAPACITY) and desc[4:6] == [1 << bit, 0]
    base, count, cursor = desc[:3]
    assert base <= cursor < base + count*28 and (cursor-base)%28 == 0
    # Dynamic T_LOGGERMEMORY uses the native MEM0 heap (C55...), unlike
    # card-payload allocations in MEM1. Require its actual ownership marker.
    static = desc[7] == 0xC0727508 and desc[6] == 0 and count == 256
    dynamic = desc[7] == 0xC0727374 and desc[6] == 1 and count == CAPACITY
    assert static or dynamic
    assert (static and 0xC3000000 <= base < base+count*28 <= 0xC4000000) or (dynamic and 0xC5000000 <= base < base+count*28 <= 0xC6000000)
    return ptr, desc


def export(dest):
    assert C.live.putfile.mem_get(LOGGER, 2, tries=1) == [0, 0]
    report = {}
    for bit, name in CATEGORIES:
        ptr, desc = header(bit)
        data = bytearray()
        n = desc[1]*7
        for offset in range(0, n, 128):
            words = C.live.putfile.mem_get(desc[0]+4*offset, min(128,n-offset), tries=1)
            data.extend(struct.pack('<%dI' % len(words), *words))
        assert header(bit) == (ptr, desc), 'native ring changed during frozen read'
        path = dest / (name + '.bin')
        assert not path.exists()
        path.write_bytes(data)
        rows = [list(struct.unpack_from('<7I', data, i*28)) for i in range(desc[1])]
        index = (desc[2]-desc[0])//28
        rows = rows[index:]+rows[:index] if desc[3] else rows[:index]
        events = [{'code':hex(w[0]),'timestamp':w[1],'thread':w[2]&255,
                   'level':(w[2]>>8)&255,'format':w[2]>>16,'values':w[3:]} for w in rows]
        (dest/(name+'.json')).write_text(json.dumps(events,indent=2)+'\n')
        report[name] = {'descriptor_address':hex(ptr),'descriptor':desc,
                        'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                        'events':len(events),'overwrites':desc[3]}
    (dest/'rings.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    mode, label = sys.argv[1:]
    assert mode in ('prepare','finish')
    dest = C.HERE/label
    dest.mkdir()
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        idle(dest)
        if mode == 'prepare':
            before = C.live.putfile.mem_get(LOGGER, 8, tries=1)
            assert before[:4] == [0xFFFFFFFF,0xFFFFFFFF,0,2], before
            for bit, _ in CATEGORIES: assert header(bit)[1][1] == 256
            (dest/'settings-before.json').write_text(json.dumps(before)+'\n')
            C.live.checked_sh('log inact ALL')
            export(dest)
            for _, name in CATEGORIES:
                C.live.checked_sh('log expand '+name+' '+str(CAPACITY))
            for bit, _ in CATEGORIES:
                assert header(bit)[1][1:4] == [CAPACITY,header(bit)[1][0],0]
            C.live.checked_sh('log level DEBUG')
            C.live.checked_sh('log act RECMGR RECMGR2')
            armed = C.live.putfile.mem_get(LOGGER,4,tries=1)
            assert armed == [0x800004,0,0,0], armed
            (dest/'settings-armed.json').write_text(json.dumps(armed)+'\n')
        else:
            assert C.live.putfile.mem_get(LOGGER,4,tries=1) == [0x800004,0,0,0]
            C.live.checked_sh('log inact ALL')
            export(dest)
            # No-argument expand restores the firmware's original static ring.
            for _, name in CATEGORIES: C.live.checked_sh('log expand '+name)
            for bit, _ in CATEGORIES: assert header(bit)[1][1] == 256
            C.live.checked_sh('log level WARNING')
            C.live.checked_sh('log act ALL')
            restored = C.live.putfile.mem_get(LOGGER,8,tries=1)
            before = json.loads((C.HERE/(label.replace('-finished','-prepared'))/'settings-before.json').read_text())
            assert restored == before, (restored,before)
            (dest/'settings-restored.json').write_text(json.dumps(restored)+'\n')
        print(mode,label,flush=True)


if __name__ == '__main__': main()
