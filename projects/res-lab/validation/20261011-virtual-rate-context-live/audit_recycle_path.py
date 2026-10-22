"""Offline lifecycle analysis of existing native traces; no camera operations.

0x99990005 is the writer's RETURN log, not its entry or a flush trigger.
Generation starts at event5 dispatch. Match the native RAW address as well as
the recyclable slot id. A release-entry log is not a pool-return observation.
"""
from pathlib import Path
import collections
import hashlib
import json
import statistics

HERE = Path(__file__).resolve().parent
TRIALS = ('native-280-finished', 'native-280-bulk1-finished',
          'native-280-v14-finished', 'native-280-v14-gyrooff-finished')
TAGS = dict(vbuf=0x44445501, prepare=0x44440005,
            accepted_post=0x88888888, accepted_dispatch=0x44440008,
            completion=0x99990031, done_post=0x22222222,
            done_dispatch=0x44440009, release_entry=0x22220000,
            raw_free=0x66666666, writer_enter=0x99990000,
            writer_io_begin=0x99990004, writer_return=0x99990005,
            header_start=0x10110304, header_end=0x10110307)


def analyze(label):
    paths = [HERE / label / (n + '.json') for n in ('RECMGR', 'RECMGR2')]
    rows = sum((json.loads(p.read_text()) for p in paths), [])
    origin = rows[0]['timestamp']
    tick = lambda e: (e['timestamp'] - origin) & 0xffffffff
    rows.sort(key=tick)
    ev = {k: [e for e in rows if e['values'][0] == v] for k, v in TAGS.items()}
    assert len(ev['vbuf']) == 1
    vbuf = tick(ev['vbuf'][0])

    def unique(kind, slot, start, limit, raw=None):
        found = [e for e in ev[kind] if e['values'][1] == slot and
                 start <= tick(e) < limit and
                 (raw is None or e['values'][2] == raw) and
                 (kind != 'release_entry' or e['values'][2] == 0xc038c228)]
        assert len(found) == 1, (label, kind, slot, start, limit, len(found))
        return found[0]

    spans = []
    for prepare in ev['prepare']:
        slot, raw = prepare['values'][1], prepare['values'][3]
        start = tick(prepare)
        following = [tick(e) for e in ev['prepare']
                     if e['values'][1] == slot and tick(e) > start]
        limit = min(following, default=0x100000000)
        p8 = unique('accepted_post', slot, start, limit)
        d8 = unique('accepted_dispatch', slot, tick(p8), limit)
        p9 = unique('done_post', slot, start, limit)
        d9 = unique('done_dispatch', slot, tick(p9), limit)
        complete = unique('completion', slot, start, limit, raw)
        free = unique('raw_free', slot, tick(d9), limit, raw)
        release = unique('release_entry', slot, tick(d9), limit)
        returned = unique('writer_return', slot, start, limit, raw)
        entered = unique('writer_enter', slot, start, limit)
        assert tick(complete) <= tick(p9) <= tick(d9) <= tick(free) <= tick(release)
        # The callback can precede the writer-return log in the same call.
        assert tick(entered) <= tick(p8) <= tick(returned)
        spans.append({
            'slot': slot, 'raw_buffer': hex(raw), 'generation_start_ms': start/1000,
            'accepted_post_ms': tick(p8)/1000, 'accepted_dispatch_ms': tick(d8)/1000,
            'accepted_delay_ms': (tick(d8)-tick(p8))/1000,
            'accepted_headers_between': sum(tick(p8) < tick(e) < tick(d8)
                                             for e in ev['header_start']),
            'writer_enter_ms': tick(entered)/1000,
            'writer_return_ms': tick(returned)/1000,
            'complete_ms': tick(complete)/1000, 'done_post_ms': tick(p9)/1000,
            'done_dispatch_ms': tick(d9)/1000,
            'done_delay_ms': (tick(d9)-tick(p9))/1000,
            'done_headers_between': sum(tick(p9) < tick(e) < tick(d9)
                                         for e in ev['header_start']),
            'done_post_before_vbuf': tick(p9) < vbuf,
            'raw_free_ms': tick(free)/1000, 'release_entry_ms': tick(release)/1000,
            'release_after_dispatch_ms': (tick(release)-tick(d9))/1000,
        })
    warning = [e for e in rows if 0xc03a9580 <= int(e['code'], 16) < 0xc03a9690]
    hdr = [(tick(b)-tick(a))/1000 for a,b in zip(ev['header_start'], ev['header_end'])]
    assert len(ev['header_start']) == len(ev['header_end']) == len(spans)
    return dict(trial=label, origin_us=origin, vbuf_ms=vbuf/1000,
        sources=[dict(path=str(p.relative_to(HERE)), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                 for p in paths],
        counts={k: len(v) for k,v in ev.items()},
        before_vbuf={k: sum(tick(e)<vbuf for e in v) for k,v in ev.items()},
        queue_allocation_warning_count=len(warning),
        threads={k: dict(collections.Counter(e['thread'] for e in v)) for k,v in ev.items()},
        header_total_ms=sum(hdr), header_median_ms=statistics.median(hdr),
        frames=spans,
        limitations=['DEBUG alters scheduling; thread IDs are not priorities.',
                    'The observer logs before queue submission; allocation warnings are absent, '
                    'but the low-level send return is not logged.',
                    'Release-entry pairing requires caller C038C228; later error cleanup '
                    'can reuse a slot without an event5 success. RAW-free log precedes '
                    'its allocator call; release-entry is not a '
                    'descriptor-pool-return trace. Standby pool readback is separate evidence.',
                    'Delays whose completion arrives after vbuf include stop/drain behavior.',
                    'These are earlier SD trials, not the later H2 SSD trials.'])


if __name__ == '__main__':
    reports = [analyze(label) for label in TRIALS]
    output = HERE / 'recycle-source-audit'
    output.mkdir(exist_ok=True)
    (output/'traces.json').write_text(json.dumps(reports, indent=2)+'\n')
    for r in reports:
        print(r['trial'], 'event8/9', r['counts']['accepted_post'], r['counts']['done_post'],
              'before vbuf RAWfree', r['before_vbuf']['raw_free'],
              'first delays', r['frames'][0]['accepted_delay_ms'], r['frames'][0]['done_delay_ms'])
