"""Read the current test card using maintained file tools; no card writes."""
import fcntl
import hashlib
import json
from pathlib import Path
import socket
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'projects/res-lab/validation/20261009-oncamera'))
sys.path.insert(0, str(ROOT / 'projects/res-lab/validation/20261012-m12-240-live'))
import live_camera as live
import backup as B

live.LOG = HERE / 'commands.jsonl'
B.live = live
dest = HERE / 'backup'
dest.mkdir(exist_ok=True)
proof = {'written_to_card': False, 'phase': 'reading', 'files': {}}
save = lambda: (dest / 'manifest.json').write_text(json.dumps(proof, indent=2) + '\n')
with open('/tmp/fp-af-fusion.lock', 'r') as lease:
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect(live.putfile.SOCK)
        owner = struct.unpack('i', conn.getsockopt(0, 2, 4))[0]
        assert owner == 82146, owner
        conn.sendall(b'STATUS\n')
        proof['daemon'] = conn.recv(4096).decode()
        proof['daemon_pid'] = owner
    proof['idle'] = B.idle()
    assert live.putfile.mem_get(live.putfile.ECHO_SLOT, tries=1) == [live.putfile.ECHO_ORIG]
    root_listing = live.checked_sh('dir')
    folder_listing = live.checked_sh('dir \\fpSup')
    proof['root_listing'] = root_listing
    proof['folder_listing'] = folder_listing
    todo = {'\\AutoRun.txt': B.entries(root_listing)['AutoRun.txt']}
    for name, size in B.entries(folder_listing).items():
        if name.upper().endswith('.BIN') or name == 'LOAD.LOG':
            todo['\\fpSup\\' + name] = size
    save()
    for remote, size in todo.items():
        local = dest / remote.lstrip('\\').replace('\\', '__')
        data = B.fetch(remote, local, size)
        proof['files'][remote] = {'file': local.name, 'bytes': len(data),
                                  'sha256': hashlib.sha256(data).hexdigest()}
        save()
        print('Backed up', remote, size, flush=True)
    proof['phase'] = 'complete'
    assert live.putfile.mem_get(live.putfile.ECHO_SLOT, tries=1) == [live.putfile.ECHO_ORIG]
    save()
    print(json.dumps(proof['files'], indent=2))
