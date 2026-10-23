"""Read-only review of the current camera and deployed batch-policy identity.

No REC, reboot, log clearing, setting changes or card file I/O. Reuses the
maintained transport, bounded LOSS record scanner and known consumer verifier.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / '20261012-m12-240-live'))
import camera as C
C.live.LOG = HERE / 'commands.jsonl'
sys.path.insert(0, str(ROOT / 'fpSup/lossless'))
import card_status as cs

MODULE = ROOT / 'projects/lossless-sup/validation/20261012-lossless-independent/module'


def inspect(native_output=None):
    report = {'camera_settings_changed': False}
    report['idle'] = C.idle()
    report['record_log'] = C.live.checked_sh('rec log-out')
    report['settings'] = {n: C.live.checked_sh(n).strip() for n in (
        'status get app_current', 'sdcard slot', 'menu SetMovRecFormat',
        'menu SetMovRecSize', 'menu SetMovCinemaDNGQuality',
        'menu SetMovFramerate', 'gui geti MV_fpLossless')}
    if native_output is not None:
        assert not native_output.exists()
        native_output.write_text(json.dumps(report, indent=2) + '\n')
    pf = C.live.putfile
    found = cs.find_record(lambda at, n: pf.mem_get(at, n, tries=1))
    assert found, 'No verified LOSS record'
    record, state, base = found
    meta = json.loads((MODULE / 'build.json').read_text())['blob']
    assert state == base + meta['state_off']
    assert pf.mem_get(record + 44, tries=1)[0] == meta['blob_len']
    # Loader-v3 sup header is 32 bytes. The compiled C body is immutable;
    # launcher runtime pointers and settings are deliberately excluded.
    binary = (MODULE / '10LOSS.BIN').read_bytes()
    start, size = meta['c_base'], meta['c_text']
    code = pf.read_bulk(base + start, size, 'tagged')
    assert code == binary[32 + start:32 + start + size], 'LOSS C body differs'
    fields = json.loads((MODULE / 'layout.json').read_text())['fields']
    values = {}
    for name, off in fields.items():
        if name in cs.ARRAY_WORDS or name in ('trace', 'elog'):
            continue
        assert 0 <= off <= meta['state_bytes'] - 4
        values[name] = pf.mem_get(state + off, tries=1)[0]
    assert values['magic'] == 0x44524143
    pool = pf.mem_get(0xC2F1F3D8, tries=1)[0]
    assert 0xC3000000 <= pool <= 0xC8000000 - 0x1130 and not pool & 3
    registry = []
    for index in (0, 64):
        registry.extend(pf.mem_get(0xC351FF48 + index * 4,
                                   min(64, 96 - index), tries=1))
    report['loss'] = {'record': hex(record), 'base': hex(base), 'state': hex(state),
        'immutable_c_sha256': hashlib.sha256(code).hexdigest(),
        'values': values, 'descriptors_free': pf.mem_get(pool + 0x112C, tries=1)[0],
        'registry_occupied': sum(0x40000000 <= w < 0xE0000000 and not w & 3 for w in registry)}
    report['hooks'] = {hex(at): hex(pf.mem_get(at, tries=1)[0])
                       for at in (0xC0377118, 0xC063F828)}
    report['consumer'] = C.snapshot()
    report['idle_after'] = C.idle()
    return report


if __name__ == '__main__':
    output = HERE / (sys.argv[1] + '.json')
    assert not output.exists()
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = inspect()
        output.write_text(json.dumps(report, indent=2) + '\n')
    v = report['loss']['values']
    print(json.dumps({'record_log': report['record_log'], 'settings': report['settings'],
        'descriptors_free': report['loss']['descriptors_free'],
        'selected_consumer_entry': report['consumer'].get('picked_entry'),
        'policy_and_stop': {k: n for k, n in v.items() if k.startswith('bulk_policy.') or
            k.startswith('record_diag.') and k not in cs.ARRAY_WORDS or k in (
            'rec_menu_off', 'rec_admitted', 'rec_raw', 'rec_events',
            'rec.workspace.last_result', 'rec.facts.seen.fps_num',
            'rec.facts.seen.fps_den', 'hold.stalls', 'hold_b.stalls')}}, indent=2), flush=True)
