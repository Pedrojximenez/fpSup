"""Offline event timing; caller PCs and format payloads remain separate.

Header brackets include Gyro2 and native copy. A completion callback precedes
its RAW-task descriptor release; neither proves durable media integrity.
"""
import json, os, statistics, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
TAGS={'vbuf':0x44445501,'submitted':0x99990005,'completed':0x99990031,
      'released':0x22220000,'header_begin':0x10110306,'header_end':0x10110307,
      'sensor_callback':0x54545454}
EXPECTED_HEADERS=int(os.environ.get('RESLAB_TRACE_EXPECTED_HEADERS','94'))
assert 0 < EXPECTED_HEADERS <= 2000
HEADER_CONTEXT=os.environ.get('RESLAB_TRACE_HEADER_CONTEXT','Gyro2 and native copy')

for label in sys.argv[1:]:
    dest=HERE/label
    rows=sum((json.loads((dest/(name+'.json')).read_text()) for name in ('RECMGR','RECMGR2')),[])
    origin=rows[0]['timestamp']
    tick=lambda e:(e['timestamp']-origin)&0xFFFFFFFF
    rows.sort(key=tick)
    events={name:[e for e in rows if e['values'][0]==tag] for name,tag in TAGS.items()}
    assert len(events['vbuf'])==1
    end=tick(events['vbuf'][0])
    report={'origin_us':origin,'vbuf_ms':end/1000,'vbuf_payload':events['vbuf'][0]['values'],
            'before_vbuf':{k:sum(tick(e)<end for e in events[k]) for k in ('submitted','completed','released')},
            'first_written_frames':[], 'expected_headers':EXPECTED_HEADERS,
            'header_context':HEADER_CONTEXT,
            'limitations':'DEBUG changes scheduling; header context is supplied from the verified trial; callbacks/releases are not durable-media or no-mosaic proof.'}
    for req in events['submitted'][:3]:
        frame=req['values'][1]
        # Native slot ids recycle after release. Bound one lifecycle by the
        # next submission of this slot and also match its RAW buffer address.
        following=[tick(e) for e in events['submitted']
                   if e['values'][1]==frame and tick(e)>tick(req)]
        boundary=min(following) if following else 0x100000000
        done=[e for e in events['completed'] if e['values'][1:3]==req['values'][1:3]
              and tick(req)<=tick(e)<boundary]
        assert len(done)==1
        free=[e for e in events['released'] if e['values'][1]==frame
              and tick(done[0])<=tick(e)<boundary]
        assert len(done)==len(free)==1
        report['first_written_frames'].append({'slot':frame,'raw_buffer':hex(req['values'][2]),'submit_ms':tick(req)/1000,
             'complete_ms':tick(done[0])/1000,'release_ms':tick(free[0])/1000,
             'complete_to_release_ms':(tick(free[0])-tick(done[0]))/1000})
    begin,endhdr=events['header_begin'],events['header_end']
    assert len(begin)==len(endhdr)==EXPECTED_HEADERS
    assert all(tick(s)<=tick(e) for s,e in zip(begin,endhdr))
    spans=[(tick(e)-tick(s))/1000 for s,e in zip(begin,endhdr)]
    report['header_bracket_ms']={'min':min(spans),'median':statistics.median(spans),'max':max(spans)}
    callbacks=events['sensor_callback']
    if callbacks:
        gaps=[tick(b)-tick(a) for a,b in zip(callbacks,callbacks[1:])]
        report['sensor_callbacks']={'count':len(callbacks),'median_gap_us':statistics.median(gaps),
            'limitation':'callback cadence does not establish exposure or complete recorded frames'}
    path=dest/'summary.json';assert not path.exists();path.write_text(json.dumps(report,indent=2)+'\n')
    print(label,json.dumps(report),flush=True)
