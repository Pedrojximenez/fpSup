#!/usr/bin/env python3
"""Bounded original-instruction boundary tests; synthetic RAM/services only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_PROT_READ, UC_PROT_EXEC, UC_PROT_WRITE, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

BASE=0xC0000000
RAM=0x10000000
STOP=0x20000000
COMP=RAM+0x1000
EVENT=RAM+0x2000
CTX=RAM+0x3000
ARG=RAM+0x4000
NATIVE=((0xC05FBFB8,0xC05FC126),(0xC05D63A8,0xC05D63D2),
        (0xC05D6878,0xC05D68A4),(0xC05FAD48,0xC05FAD60),
        (0xC05FADCC,0xC05FB018),(0xC06012D0,0xC0601400))
STUBS={0xC05D6400:'property_get',0xC05E9550:'timer',0xC05E93A8:'dispatch',
       0xC05D6038:'integer_core',0xC05D64E0:'float_core',
       0xC05D7148:'userdata',0xC0601140:'property_sync',0xC05FA998:'value_event',
       0xC0015058:'memset',0xC06011F0:'integer_only_normalization',
       0xC05E9440:'held_key_count',0xC05E9468:'held_key_at'}

class Probe:
    def __init__(self,data):
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        self.uc.mem_map(BASE,(len(data)+4095)&~4095)
        self.uc.mem_write(BASE,data)
        self.uc.mem_protect(BASE,(len(data)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
        self.uc.mem_map(RAM,0x10000,UC_PROT_READ|UC_PROT_WRITE)
        self.uc.mem_map(STOP,4096,UC_PROT_READ|UC_PROT_EXEC)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2,0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        self.uc.hook_add(UC_HOOK_CODE,self.step)
        self.uc.hook_add(UC_HOOK_MEM_WRITE,self.write_guard)
        self.calls=[]
        self.props={0:1,1:2,2:1,3:13,4:0}
        self.pcs=[]
    def rd(self,addr): return struct.unpack('<I',self.uc.mem_read(addr,4))[0]
    def wr(self,addr,v):
        assert RAM <= addr and addr+4 <= RAM+0x10000
        self.uc.mem_write(addr,struct.pack('<I',v&0xffffffff))
    def write_guard(self,uc,access,addr,size,value,data):
        assert RAM <= addr and addr+size <= RAM+0x10000, 'native write outside synthetic RAM'
    def reg(self,n): return self.uc.reg_read((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)[n])
    def step(self,uc,pc,size,_):
        if pc==STOP: uc.emu_stop(); return
        if pc not in STUBS:
            if not any(a<=pc and pc+size<=b for a,b in NATIVE): raise AssertionError('unlisted PC '+hex(pc))
            self.pcs.append(pc); return
        args=[self.reg(i) for i in range(4)]
        sp=uc.reg_read(UC_ARM_REG_SP)
        call={'service':STUBS[pc],'args':args}
        self.calls.append(call)
        if pc==0xC05D6400:
            assert args[0]==COMP and args[1] in self.props
            self.wr(args[2],self.props[args[1]])
        elif pc==0xC05D7148:
            assert args[0]==COMP
            self.wr(args[1],CTX)
        elif pc in (0xC05D6038,0xC05D64E0):
            call['property']=self.rd(sp)
            call['raw_value']=self.rd(self.rd(sp+4))
        elif pc==0xC0015058:
            assert RAM<=args[0] and args[0]+args[2]<=RAM+0x10000
            uc.mem_write(args[0],bytes([args[1]&255])*args[2])
        elif pc==0xC06011F0:
            val=struct.unpack('<f',uc.mem_read(args[0],4))[0]
            assert val in (-1.0,0.0,1.0,2.0), 'normalization stub only valid for these exact small integers'
        elif pc==0xC05E9440:
            self.wr(args[1],1)
        elif pc==0xC05E9468:
            assert args[1]==0
            self.wr(args[2],13)
        uc.reg_write(UC_ARM_REG_R0,0)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def run(self,entry,args):
        for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args): self.uc.reg_write(reg,v)
        sp=RAM+0xF000
        self.uc.reg_write(UC_ARM_REG_SP,sp)
        self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
        self.uc.emu_start(entry|1,STOP,timeout=250000,count=5000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==STOP
        assert self.uc.reg_read(UC_ARM_REG_SP)==sp
        return self.uc.reg_read(UC_ARM_REG_R0)

def main():
    if not __debug__:
        raise RuntimeError('Do not disable test assertions with -O')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seg0',required=True,type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    data=args.seg0.read_bytes()
    assert len(data)==49245696 and hashlib.sha256(data).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
    cases=[]
    for typ in (0,1):
        p=Probe(data);p.props[0]=typ;p.wr(EVENT,0x40);p.wr(EVENT+8,13)
        assert p.run(0xC05FBFB8,[COMP,EVENT,0,ARG])==0
        dispatched=[c for c in p.calls if c['service']=='dispatch']
        assert len(dispatched)==typ
        if typ: assert dispatched[0]['args'][3]==0x2500
        cases.append({'name':'keypress_mask_'+str(typ),'pass':True,'dispatch_count':len(dispatched),'native_steps':len(p.pcs)})
    p=Probe(data);p.props[0]=0;p.wr(EVENT,0x40);p.wr(EVENT+8,13)
    assert p.run(0xC05FBFB8,[COMP,EVENT,3,ARG])==0
    dispatched=[c for c in p.calls if c['service']=='dispatch']
    assert len(dispatched)==1 and dispatched[0]['args'][3]==0x2500
    cases.append({'name':'mask_zero_does_not_cancel_existing_repeat_phase3','pass':True,
                  'dispatch_count':1,'native_steps':len(p.pcs)})
    for entry,service in ((0xC05D63A8,'integer_core'),(0xC05D6878,'float_core')):
        p=Probe(data);p.wr(COMP+0x14,13);p.uc.reg_write(UC_ARM_REG_S0,0x3f800000)
        assert p.run(entry,[COMP,1,7,0])==0
        call=next(c for c in p.calls if c['service']==service)
        assert call['args']==[COMP,0,1,0] and call['property']==1
        assert call['raw_value']==(7 if service=='integer_core' else 0x3f800000)
        cases.append({'name':service+'_wrapper_ABI','pass':True,'boundary':call,'native_steps':len(p.pcs)})
    for loop in (0,1):
        for requested in (-1.0,0.0,1.0,2.0):
            p=Probe(data)
            for off,val in ((0x14,0.0),(0x18,0.0),(0x1c,0.0),(0x20,0.0)):
                p.uc.mem_write(CTX+off,struct.pack('<f',val))
            p.wr(CTX+0x2c,loop);p.wr(CTX+0x30,1)
            p.uc.mem_write(ARG,struct.pack('<f',requested));p.wr(ARG+4,1)
            assert p.run(0xC05FAD48,[COMP,2,ARG,ARG+4])==0
            assert p.rd(CTX+0x1c)==0
            cases.append({'name':'max_zero_clamps_loop_%d_value_%s'%(loop,requested),'pass':True,'native_steps':len(p.pcs)})
    p=Probe(data)
    p.wr(CTX+0x18,0x3f800000);p.wr(CTX+0x1c,0x3f800000);p.wr(CTX+0x20,0x3f800000)
    p.wr(CTX+0x2c,1);p.wr(CTX+0x30,1);p.wr(ARG,0);p.wr(ARG+4,1)
    assert p.run(0xC05FAD48,[COMP,1,ARG,ARG+4])==0
    assert p.rd(CTX+0x18)==0 and p.rd(CTX+0x1c)==0
    cases.append({'name':'lower_max_one_to_zero_clamps_current_one','pass':True,'native_steps':len(p.pcs)})
    report=json.dumps({'runtime_ready':False,'firmware_sha256':hashlib.sha256(data).hexdigest(),
                      'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      'native_intervals':[[hex(a),hex(b)] for a,b in NATIVE],
                      'stubs':{hex(a):n for a,n in STUBS.items()},'cases':cases,'passed':len(cases)},indent=2)
    if args.report:
        with args.report.open('x') as stream: stream.write(report+'\n')
    print(report)

if __name__=='__main__': main()
