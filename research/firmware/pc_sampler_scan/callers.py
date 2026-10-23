import struct,sys
r=open(__import__('os').path.join(__import__('os').path.dirname(__file__),'../../../out/seg0_c0000000.bin'),'rb').read()
T=int(sys.argv[1],16); B=0xc0000000; out=[]
for off in range(0,len(r)-3,4):
    v=struct.unpack_from('<I',r,off)[0]
    if (v&0x0F000000)==0x0B000000 and v>>28!=0xF:
        imm=v&0xffffff; imm=imm-(1<<24) if imm&0x800000 else imm
        if B+off+8+imm*4==T: out.append(('A',B+off))
    if v>>25==0x7D:  # BLX imm
        imm=v&0xffffff; imm=imm-(1<<24) if imm&0x800000 else imm
        if B+off+8+imm*4+((v>>24)&1)*2==T: out.append(('A>T',B+off))
for off in range(0,len(r)-3,2):
    h1,h2=struct.unpack_from('<HH',r,off)
    if (h1&0xF800)==0xF000 and (h2&0xC000)==0xC000:
        S=(h1>>10)&1; J1=(h2>>13)&1; J2=(h2>>11)&1; I1=1-(J1^S); I2=1-(J2^S)
        imm=(S<<24)|(I1<<23)|(I2<<22)|((h1&0x3ff)<<12)|((h2&0x7ff)<<1)
        if S: imm-=1<<25
        pc=B+off+4
        if h2&0x1000: tgt=pc+imm
        else: tgt=(pc&~3)+imm
        if tgt==T: out.append(('T',B+off))
for k,a in out: print(k,hex(a))
