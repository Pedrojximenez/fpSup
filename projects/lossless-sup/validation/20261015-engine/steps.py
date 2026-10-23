import sys,json; sys.path[:0]=['../../../../fpSup/fp_usb_shell','../../../../fpSup/lossless']
import putfile as pf, card_status as cs
f=json.load(open(sys.argv[1]))['fields']; _,st,_=cs.find_record(pf.mem_get)
s=pf.mem_get(st+f['hold.job.diag_submit_us'],5); fi=pf.mem_get(st+f['hold.job.diag_finish_us'],5); n=pf.mem_get(st+f['hold.job.diag_n'])[0] or 1
print('jobs',n,'engine_release',pf.mem_get(st+f['engine_release'])[0],'engine enable now',pf.mem_get(0x300D0074)[0]&1)
print('submit us/job  F_INIT %.1f open %.1f band %.1f submit %.1f reset+start %.1f' % tuple(x/n for x in s))
print('finish us/job  eoi+tiles %.1f total %.1f pad %.1f table %.1f close %.1f' % tuple(x/n for x in fi))
json.dump({'jobs':n,'submit':s,'finish':fi},open(sys.argv[2],'w'))
