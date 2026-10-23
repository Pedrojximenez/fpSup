import struct,sys
r=open(__import__('os').path.join(__import__('os').path.dirname(__file__),'../../../out/seg0_c0000000.bin'),'rb').read()
targets=set(int(x,16) for x in sys.argv[1:])
# ARM movw/movt: movw: cond 0011 0000 imm4 Rd imm12 ; movt: cond 0011 0100
last={}
for off in range(0,len(r)-3,4):
    v=struct.unpack_from('<I',r,off)[0]
    if (v&0x0FF00000)==0x03000000:
        rd=(v>>12)&15; last[rd]=(off,((v>>16)&15)<<12|(v&0xfff))
    elif (v&0x0FF00000)==0x03400000:
        rd=(v>>12)&15
        if rd in last and off-last[rd][0]<=16:
            val=((((v>>16)&15)<<12|(v&0xfff))<<16)|last[rd][1]
            if val in targets: print('ARM',hex(0xC0000000+off),hex(val))
# Thumb2 movw: hw1=11110 i 10 0 1 0 0 imm4 ; hw2=0 imm3 Rd imm8 ; movt: 11110 i 10 1 1 0 0 imm4
lastt={}
for off in range(0,len(r)-3,2):
    h1,h2=struct.unpack_from('<HH',r,off)
    if (h1&0xFBF0)==0xF240 and not h2&0x8000:
        rd=(h2>>8)&15; imm=((h1&15)<<12)|(((h1>>10)&1)<<11)|(((h2>>12)&7)<<8)|(h2&0xff); lastt[rd]=(off,imm)
    elif (h1&0xFBF0)==0xF2C0 and not h2&0x8000:
        rd=(h2>>8)&15; imm=((h1&15)<<12)|(((h1>>10)&1)<<11)|(((h2>>12)&7)<<8)|(h2&0xff)
        if rd in lastt and 0<off-lastt[rd][0]<=16:
            val=(imm<<16)|lastt[rd][1]
            if val in targets: print('THM',hex(0xC0000000+off),hex(val))
