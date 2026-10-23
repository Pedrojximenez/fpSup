import sys,json; sys.path[:0]=['../../../../fpSup/fp_usb_shell','../../../../fpSup/lossless']
import putfile as pf, card_status as cs
f=json.load(open('build-diag/layout.json'))['fields']; _,st,_=cs.find_record(pf.mem_get)
g=lambda k,n=1: pf.mem_get(st+f[k],n)
n=g('hold.job.diag_n')[0] or 1; s=g('hold.job.diag_submit_us',5); fi=g('hold.job.diag_finish_us',5)
ht=g('hook_time',32); names=['rec','arrive','stop','flush','observe','written','event','discard']
rep={'compressed':g('hold.compressed')[0],'refused':g('hold.refused')[0],'held':g('hold.held')[0],
     'preopened':g('hold.job.preopened')[0],'preopen_failed':g('hold.job.preopen_failed')[0],
     'engine_release':g('engine_release')[0],'enable_now':pf.mem_get(0x300D0074)[0]&1,
     'tag_failed':g('flush.tag_failed')[0],'jobs':n,
     'submit_us':[round(x/n,1) for x in s],'finish_us':[round(x/n,1) for x in fi],
     'hooks_cumulative':{nm:ht[4*i:4*i+2] for i,nm in enumerate(names)}}
json.dump(rep,open(sys.argv[1],'w'),indent=1); print(rep)
