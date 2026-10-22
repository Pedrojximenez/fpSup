"""find movw/movt pairs building a given 32-bit constant (ARM + Thumb), print following ldr/str offsets"""
import sys, re
from capstone import *
d=open('/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin','rb').read();B=0xC0000000
val=int(sys.argv[1],16); lo=val&0xffff; hi=val>>16
arm=Cs(CS_ARCH_ARM,CS_MODE_ARM); th=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
LIM=0xC00000
def scan(md,step):
    for off in range(0,LIM,step):
        ins=next(md.disasm(d[off:off+4],B+off),None)
        if ins and ins.mnemonic.startswith('movw') and ins.op_str.endswith('#0x%x'%lo):
            win=list(md.disasm(d[off:off+40],B+off))[:10]
            if any(i.mnemonic.startswith('movt') and i.op_str.endswith('#0x%x'%hi) for i in win):
                print(('ARM ' if step==4 else 'THM ')+hex(B+off),' | '.join(f'{i.mnemonic} {i.op_str}' for i in win[1:7]))
scan(arm,4); scan(th,2)
