import sys,capstone
rom=open(__import__('os').path.join(__import__('os').path.dirname(__file__),'../../../out/seg0_c0000000.bin'),'rb').read()
a=int(sys.argv[1],16);n=int(sys.argv[2],16);mode=capstone.CS_MODE_THUMB if len(sys.argv)>3 else capstone.CS_MODE_ARM
md=capstone.Cs(capstone.CS_ARCH_ARM,mode)
for i in md.disasm(rom[a-0xC0000000:a-0xC0000000+n],a): print(f"{i.address:08x}  {i.mnemonic:8s} {i.op_str}")
