"""Offline decode of the captured Ver.5.02 native task-monitor rings.

C002B718 records seconds/timer ticks; C002B440 converts with the live
C2EFABD0 divisor. C0682298 attributes the interval to the earlier task.
No camera access. Cross-check the full native summary before using windows.
"""
import collections,json,re,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
TASKS={1:'inittsk',39:'DrawMgr',44:'CamSch',45:'MRecMgr',54:'SRecRaw',61:'SRecFile',124:'_VSHL',125:'FPLCODE'}

def analyze(label):
    d=json.loads((HERE/(label+'.json')).read_text())
    m=json.loads((HERE/(label+'-ring.json')).read_text())
    raw=(HERE/(label+'-ring.bin')).read_bytes()
    assert m['vtable']==[0xc002b6b0,0xc002b6e0,0xc002b718,0xc002b440]
    assert not m['monitor'][6]&15  # these captures have not wrapped
    rows=list(struct.iter_unpack('<7I',raw))
    t=[r[2]*1000000+(r[3]*100)//m['clock'][2] for r in rows]
    assert all(a<=b for a,b in zip(t,t[1:]))
    origin=t[0];t=[x-origin for x in t]
    def window(lo,hi):
        c=collections.Counter();starts=collections.defaultdict(list)
        for i,r in enumerate(rows[:-1]):
            c[r[0]]+=max(0,min(t[i+1],hi)-max(t[i],lo))
            if lo<=t[i]<hi: starts[r[0]].append(t[i])
        total=sum(c.values());assert total==hi-lo
        draws=starts[39]
        return {'lo_us':lo,'hi_us':hi,'cpu_percent':100*(total-c[1])/total,
                'task_percent':{TASKS.get(k,str(k)):100*v/total for k,v in c.items()},
                'draw_dispatch_max_gap_us':max((b-a for a,b in zip(draws,draws[1:])), default=None)}
    top=d['task_top_recording'];n=int(re.search(r'Cnt = (\d+)',top).group(1))
    native_total=int(re.search(r'Total\(Sum\)\s+(\d+)',top).group(1))
    assert t[n-1]==native_total
    native_check=window(0,native_total)
    native_cpu=float(re.search(r'CPU = ([\d.]+)',top).group(1))
    assert abs(native_check['cpu_percent']-native_cpu)<0.051
    w=window(1100000,2100000)
    v=d['after']['values']
    assert v['rec_first_frame_us']<1000000
    return {'label':label,'clip':d['new_clips'][0], 'native_summary_match':True,
            'native_summary_cpu_percent':native_cpu,'native_summary_us':native_total,
            'window':w,'bins_100ms':[window(i*100000,(i+1)*100000) for i in range(11,21)],
            'take_frames':v['take_frames'],'rec_first_frame_us':v['rec_first_frame_us'],
            'descriptors_free':d['after']['descriptors_free'],
            'worker_restored':next(x for x in d['tasks_restored'].splitlines() if '_VSHL' in x)}

result={'method':'same boot, FHD 12-bit 59.94p, 428 slots, 64 MiB; diagnostic _VSHL priority 10 in both trials, restored to 28; 1.1..2.1 seconds from first monitor record',
        'on':analyze('lag-protected-on-take'),'off':analyze('lag-protected-off-take')}
(HERE/'lag-cpu-comparison.json').write_text(json.dumps(result,indent=2))
for state in ('off','on'):
    r=result[state];w=r['window'];print(state,r['clip'],round(w['cpu_percent'],2),{k:round(w['task_percent'].get(k,0),2) for k in TASKS.values()},w['draw_dispatch_max_gap_us'])
