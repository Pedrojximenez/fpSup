import struct,sys
ROM=open('out/seg0_c0000000.bin','rb').read()
BASE=0xC0000000
def rd(va,n=4):
    off=va-BASE
    if off<0 or off+n>len(ROM): return None
    return ROM[off:off+n]
def u32(va):
    b=rd(va,4); return struct.unpack('<I',b)[0] if b else None
def cstr(va,maxn=64):
    off=va-BASE
    if off<0 or off>=len(ROM): return None
    e=ROM.find(b'\x00',off)
    return ROM[off:e].decode('latin1',errors='replace')
def find_str(s):
    b=s.encode(); res=[]; i=0
    while True:
        i=ROM.find(b,i)
        if i<0: break
        res.append(BASE+i); i+=1
    return res
if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='cmdtable':
        va=int(sys.argv[2],16); n=int(sys.argv[3])
        # table format: guess pairs of (name_ptr, func_ptr) or (name_ptr,func,...)
        # dump 4*3*n words to inspect
        for i in range(n*4):
            w=u32(va+i*4)
            s=cstr(w) if w and BASE<=w<BASE+len(ROM) else ''
            printable = s if s and all(32<=ord(c)<127 for c in s[:1]) else ''
            print(f"[{i:3}] {va+i*4:08x}: {w:08x}  {printable!r}")
    elif cmd=='findstr':
        for a in find_str(sys.argv[2]): print(f"{a:08x}")
    elif cmd=='u32':
        print(f"{u32(int(sys.argv[2],16)):08x}")
    elif cmd=='str':
        print(cstr(int(sys.argv[2],16)))

def dump_vtable(va,count):
    for i in range(count):
        w=u32(va+i*4)
        print(f"  +0x{i*4:03x} [{i:3}]: {w:08x}")
