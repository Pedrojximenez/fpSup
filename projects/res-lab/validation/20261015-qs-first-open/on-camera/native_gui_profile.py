"""One native GUI diagnostic window in fresh, guarded CINE standby.

No recording, card-file writes, log clearing or global log-level changes.
Core identity uses the maintained memory readback tool. Restore the two GUI flags enabled here. Existing GUI logs are
saved before enabling diagnostics. A full ring is reported, not treated as a
complete trace. Native duration records use millisecond deltas (C002B920).
"""
import argparse
import fcntl
import json
from pathlib import Path
import re
import time
import struct

import experiment as E
from current_screen import Screen

HERE = Path(__file__).resolve().parent
ATTR = 0xC37B71E0  # FUN_C055F0F0 returns C37B7048; attribute word is +0x198.
parser = argparse.ArgumentParser()
parser.add_argument('--variant', choices=('optimized', 'combined', 'combined-fix1', 'combined-fix2', 'combined-fix3', 'combined-fix4', 'stock'), default='optimized')
parser.add_argument('--out', type=Path, default=HERE / 'native-profile')
args = parser.parse_args()
folder = args.out.resolve()
E.live.LOG = folder.parent / 'commands.jsonl'
with open('/tmp/fp-af-fusion.lock', 'r') as lease:
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    E.daemon()
    E.B.idle()
    if args.variant == 'stock':
        assert E.pf.remote_file_size('\\fpSup\\32RESCUS.BIN') is None
        image = (E.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
        sites = (0xC043CCF8, 0xC05E6400, 0xC05D90F0, 0xC05E84D8)
        for site in sites:
            assert E.pf.mem_get(site, tries=1) == [struct.unpack_from('<I', image, site - 0xC0000000)[0]]
        state, identity = None, {'RES_Custom_present': False, 'stock_hook_sites': [hex(a) for a in sites]}
    else:
        state, identity = E.core_state(args.variant)
        assert E.pf.mem_get(state + E.L.S['QS_HITS'], tries=1) == [0], 'requires first QS after boot'
    attrs = E.pf.mem_get(ATTR, tries=1)[0]
    assert attrs is not None and attrs & 5 == 0, 'existing diagnostics must remain undisturbed'
    assert not folder.exists()
    folder.mkdir(parents=True)
    commands = E.live.checked_sh
    info = commands('log info')
    assert re.search(r'^act,\s+GUI,', info, re.M), 'do not change other log activation state'
    (folder / 'info-before.txt').write_text(info)
    (folder / 'GUI-before.txt').write_text(commands('log out GUI'))
    result = {'identity': identity, 'original_gui_attributes': attrs,
              'native_duration_units': 'milliseconds', 'log_cleared': False,
              'capture_level_changed': False}
    screen = Screen()
    result['initial_screen'] = screen.read()
    assert result['initial_screen'].startswith('LV_CINE')
    try:
        commands('gui time log 1')
        commands('gui image log 1')
        assert E.pf.mem_get(ATTR, tries=1) == [attrs | 5]
        started = time.monotonic()
        commands('key QSON', timeout_ms=30000)
        result['QSON_reply_seconds'] = time.monotonic() - started
        result['opened_screen'] = screen.read()
        assert result['opened_screen'].startswith('QS_CINE')
        commands('key QSOFF', timeout_ms=30000)
        result['released_screen'] = screen.read()
        assert result['released_screen'].startswith('QS_CINE')
        # Disable high-volume diagnostics before draining; preserve all entries.
        commands('gui image log 0')
        commands('gui time log 0')
        (folder / 'GUI-first-QS.txt').write_text(commands('log out GUI'))
        (folder / 'info-after.txt').write_text(commands('log info'))
        if state is not None:
            result['qs_hits_after_open'] = E.pf.mem_get(state + E.L.S['QS_HITS'], tries=1)[0]
            assert result['qs_hits_after_open'] > 0, 'no QS parse observed'
        else:
            assert 'qs_fps_tex_S.xci' in (folder / 'GUI-first-QS.txt').read_text(), 'no QS images observed'
        E.B.idle()
        commands('key QSON', timeout_ms=30000)  # next press closes the confirmed QS trial
        commands('key QSOFF', timeout_ms=30000)
        result['final_screen'] = screen.read()
        assert result['final_screen'].startswith('LV_CINE')
    finally:
        current = E.pf.mem_get(ATTR, tries=1)[0]
        assert current is not None and (current & ~5) == attrs, 'unknown attribute change'
        if current & 4:
            commands('gui image log 0')
        if current & 1:
            commands('gui time log 0')
        assert E.pf.mem_get(ATTR, tries=1) == [attrs]
        result['gui_attributes_restored'] = True
        (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    E.B.idle()
    print(json.dumps(result, indent=2))
