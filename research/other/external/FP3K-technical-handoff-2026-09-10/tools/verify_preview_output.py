"""Exercise the installed output-template hook and native channel copy.

Template values come from the returned camera trace. The policy-object pointer
layout comes from the stock constructors. No image rendering is simulated.
"""
import json,struct,hashlib
from pathlib import Path
from verify_fp3k_native_menu import Camera,BASE,STATE,code,syms

ROOT=Path(__file__).resolve().parents[1]
trace=(ROOT/'diagnostics/fullheight-preview-experiment-return/SSD/FP3KPV/STATE.BIN').read_bytes()
assert hashlib.sha256(trace).hexdigest()=='006aa8721725e7d961cecc94c2b481d5da3dfa0b49cb6cd52e90e55ff951e92e'
cases=[]
for name,index,owner,template in [('standby',4,0xc375eb68,0xc375e934),('record',0,0xc375ed3c,0xc2f21494)]:
    observed=trace[64+index*0x900+0x35c:64+index*0x900+0x388]
    expected=list(struct.unpack('<11I',observed));expected[0]=expected[4]=1620;expected[1]=expected[5]=1080
    for condition in ('inactive','active','other-channel','other-owner','wrong-pointer','changed-size','changed-format'):
        c=Camera();c.install();u=c.u
        u.mem_map(0xc375e000,4096);u.mem_map(0xc2f21000,4096)
        c.put(owner,template,3,0,0,0,0,0,0,0xc0bd0318)
        u.mem_write(template,observed)
        c.put(STATE+16,int(condition!='inactive'))
        arg=owner;channel=0
        if condition=='other-channel':channel=1
        if condition=='other-owner':arg=0xc375e000;c.put(arg,template)
        if condition=='wrong-pointer':c.put(owner,template+4)
        if condition=='changed-size':c.put(template,1234)
        if condition=='changed-format':c.put(template+28,3)
        selected=c.run(0xc0437e98,arg,channel)
        if condition=='active':
            assert selected==BASE+syms['preview_output_template']
            assert list(struct.unpack('<11I',u.mem_read(selected,44)))==expected
            before=bytes(u.mem_read(template,44))
            # Execute native channel descriptor copy with the selected template.
            dest=0x10001000
            c.run(0xc0436538,dest,selected,0x49801000,3)
            assert bytes(u.mem_read(dest+4,44))==struct.pack('<11I',*expected)
            assert c.get(dest)==0x49801000 and c.get(dest+48)==3
            assert bytes(u.mem_read(template,44))==before
        else:
            assert selected==c.get(arg+channel*8),(condition,hex(selected))
        cases.append(dict(case=name+'-'+condition,passed=True))
import verify_preview_candidate as native
pool_cases=[]
for name,index in [('standby',4),('record',0)]:
    r=trace[64+index*0x900:64+(index+1)*0x900]
    native.u.mem_write(native.SOURCE,r[0x1a0:0x200])
    native.put(native.SOURCE+4,[native.PARAM])
    native.u.mem_write(native.PARAM,r[0x200:0x30c])
    native.run(0xc0435428,native.SOURCE,writes=[(native.SOURCE+0x10,native.SOURCE+0x58)])
    before=native.get(native.SOURCE+0x10,18)
    assert struct.pack('<18I',*before)==r[0x1b0:0x1f8]
    native.put(native.SOURCE+8,[1620,1080])
    native.run(0xc0435428,native.SOURCE,writes=[(native.SOURCE+0x10,native.SOURCE+0x58)])
    after=native.get(native.SOURCE+0x10,18)
    assert all(a<=b for a,b in zip(after,before)),(name,before,after)
    pool_cases.append(dict(case=name,before=before,after=after,passed=True))
report=dict(payload_sha256=hashlib.sha256(code).hexdigest(),cases=cases,pool_cases=pool_cases,
    output=[1620,1080],trace_sha256=hashlib.sha256(trace).hexdigest(),
    limitations='Installed ARM hook, stock accessor fallback and stock channel-copy routine executed. Policy objects are reconstructed from native constructors; templates are observed camera values. Upstream selection lifecycle, actual allocation, compositor, LCD aspect and visual framing are not emulated.')
(ROOT/'prototype/development/native-menu/preview-output-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(cases),'output-template cases')
