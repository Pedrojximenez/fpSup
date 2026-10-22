import capstone,struct,sys
ROM=open('out/seg0_c0000000.bin','rb').read()
BASE=0xC0000000
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_ARM)
md.detail=False
def dis(va,n=40):
    off=va-BASE
    code=ROM[off:off+n*4]
    for ins in md.disasm(code,va):
        print(f"{ins.address:08x}: {ins.mnemonic:8} {ins.op_str}")
        if ins.mnemonic in ('bx','pop') and 'pc' in ins.op_str: 
            pass
if __name__=='__main__':
    va=int(sys.argv[1],16); n=int(sys.argv[2]) if len(sys.argv)>2 else 40
    dis(va,n)
