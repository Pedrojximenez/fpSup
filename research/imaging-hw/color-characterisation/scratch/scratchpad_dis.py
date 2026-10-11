import sys,struct
from capstone import *
base=0xC0000000
f=open('out/MAIN_c0000000.bin','rb').read()
md=Cs(CS_ARCH_ARM,CS_MODE_ARM)
md.detail=True
def u32(addr):
    o=addr-base; return struct.unpack('<I',f[o:o+4])[0]
def rdstr(addr,n=48):
    o=addr-base; s=f[o:o+n].split(b'\0')[0]
    try: return s.decode('ascii','replace')
    except: return ''
def dis(addr,count=60):
    o=addr-base
    code=f[o:o+count*4]
    for ins in md.disasm(code,addr):
        note=''
        # annotate immediates / literal pool loads
        if ins.mnemonic.startswith('ldr') and '[pc' in ins.op_str:
            # compute literal
            try:
                # find #imm
                import re
                m=re.search(r'\[pc, #(-?\d+)\]',ins.op_str)
                if m:
                    lit=ins.address+8+int(m.group(1))
                    val=u32(lit)
                    s=rdstr(val)
                    note=f"  ; =0x{val:08x} {('->'+repr(s)) if s else ''}"
            except Exception as e: note=str(e)
        if ins.mnemonic in ('bl','b','blx') :
            note='  ; -> '+ins.op_str
        print(f"0x{ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}{note}")
if __name__=='__main__':
    a=int(sys.argv[1],16); c=int(sys.argv[2]) if len(sys.argv)>2 else 60
    dis(a,c)
