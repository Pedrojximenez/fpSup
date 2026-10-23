"""Join same-boot native task dispatch and bounded LOSS phase intervals."""
import json,struct,collections,re,sys,bisect
from pathlib import Path
HERE=Path(__file__).resolve().parent
label=sys.argv[1];trial=json.loads((HERE/(label+'.json')).read_text())
meta=json.loads((HERE/(label+'-ring.json')).read_text());ph=json.loads((HERE/(label+'-phases.json')).read_text())
assert trial['after']['boot']==ph['boot'];assert not meta['monitor'][6]&15
rows=list(struct.iter_unpack('<7I',(HERE/(label+'-ring.bin')).read_bytes()))
ts=[r[2]*1000000+r[3]*100//meta['clock'][2] for r in rows];origin=ts[0];t=[x-origin for x in ts]
assert all(a<=b for a,b in zip(t,t[1:]))
n=int(re.search(r'Cnt = (\d+)',trial['task_top_recording']).group(1))
native_total=int(re.search(r'Total\(Sum\)\s+(\d+)',trial['task_top_recording']).group(1))
assert native_total in t  # printed count may include switches during summary output
names={}
for line in trial['tasks_raised'].splitlines():
 parts=line.split('|')
 if len(parts)>=3 and re.match(r'\d+\(',parts[0].strip()):names[int(parts[0].split('(')[0])]=parts[1].strip()
codec_id=next(i for i,name in names.items() if name=='FPLCODE')
def intervals(lo,hi):
 c=collections.Counter();k=max(0,bisect.bisect_right(t,lo)-1)
 while k<len(rows)-1 and t[k]<hi:
  c[rows[k][0]]+=max(0,min(t[k+1],hi)-max(t[k],lo));k+=1
 return c
check=intervals(0,native_total)
native_cpu=float(re.search(r'CPU = ([\d.]+)',trial['task_top_recording']).group(1))
assert abs(100*(1-check[1]/native_total)-native_cpu)<.051
lo,hi=1100000,2100000
assert trial['after']['values']['rec_first_frame_us']<1000000
cpu=intervals(lo,hi);total=sum(cpu.values());assert total==hi-lo
win={'cpu_percent':100*(1-cpu[1]/total),'task_percent':{names.get(k,str(k)):v*100/total for k,v in cpu.items()}}
agg=collections.defaultdict(list);details=[]
for lane,data in ph['lanes'].items():
 assert len(data)==trial['after']['values'][lane+'.profile_n'], 'phase records belong to another take'
 for phase,start,end,ident in data:
  s=(start-origin)&0xffffffff
  if s>=0x80000000:s-=0x100000000
  e=s+((end-start)&0xffffffff)
  if s<lo or e>hi:continue
  expected=codec_id if phase in (4,5) else 45
  c=intervals(s,e);us=e-s;run=c[expected]
  agg[str(phase)].append((us,run));details.append({'phase':phase,'lane':lane,'start':s,'end':e,'id':ident,'cpuUs':run})
assert set(agg)==set('12345'), 'missing phase intervals in the matched observation window'
result={'label':label,'clip':trial['new_clips'],'boot':ph['boot'],'codecTask':codec_id,'window':win,'windowUs':[lo,hi],
        'phases':{k:{'count':len(v),'meanUs':sum(x[0] for x in v)/len(v),'cpuMeanUs':sum(x[1] for x in v)/len(v),'cpuSumUs':sum(x[1] for x in v),'maxUs':max(x[0] for x in v)} for k,v in agg.items()},'intervals':details}
(HERE/(label+'-analysis.json')).write_text(json.dumps(result,indent=2))
print(label,win)
for k,v in result['phases'].items():print(k,{x:round(y,2) for x,y in v.items()})
