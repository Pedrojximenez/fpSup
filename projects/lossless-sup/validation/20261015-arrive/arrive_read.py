import sys,json; sys.path[:0]=['../../../../fpSup/fp_usb_shell','../../../../fpSup/lossless']
import putfile as pf, card_status as cs
f=json.load(open('build-diag/layout.json'))['fields']; _,st,_=cs.find_record(pf.mem_get)
g=lambda k: pf.mem_get(st+f[k])[0]
r={}
for l in ('hold','hold_b'):
    for k in ('collect_us','collect_n','take_us','take_n','dma_us','dma_n','copy_us','copy_n','enq_n','enq_us'):
        r[f'{l}.{k}']=g(f'{l}.diag_{k}')
ht=pf.mem_get(st+f['hook_time'],8); r['arrive_calls'],r['arrive_us']=ht[4],ht[5]
r['compressed']=g('hold.compressed'); r['card_enq_n'],r['card_enq_us']=g('enq_n'),g('enq_us')
json.dump(r,open(sys.argv[1],'w'),indent=1)
a=lambda us,n: round(us/n,1) if n else 0
print('arrive', r['arrive_calls'],'calls', a(r['arrive_us'],r['arrive_calls']),'us/call (cumulative since boot)')
print('collect', r['hold.collect_n'],'frames', a(r['hold.collect_us'],r['hold.collect_n']),'us/frame  | take', r['hold.take_n'], a(r['hold.take_us'],r['hold.take_n']),'us/call')
for l in ('hold','hold_b'):
    print(l,'dma',r[f'{l}.dma_n'],a(r[f'{l}.dma_us'],r[f'{l}.dma_n']),'us  copy',r[f'{l}.copy_n'],a(r[f'{l}.copy_us'],r[f'{l}.copy_n']),'us  enqueue',r[f'{l}.enq_n'],a(r[f'{l}.enq_us'],r[f'{l}.enq_n']),'us')
print('card enqueue (first frame / not held)', r['card_enq_n'], a(r['card_enq_us'],r['card_enq_n']))
