"""Read-only diagnostic preview of the TIFF big-endian packed RAW12 samples."""
import json,pathlib,struct,sys,zlib
path,out=map(pathlib.Path,sys.argv[1:3]);d=path.read_bytes()
assert d[:2]==b'II';at=struct.unpack_from('<I',d,4)[0];tags={}
for i in range(struct.unpack_from('<H',d,at)[0]):
    e=at+2+12*i;t,k,n,v=struct.unpack_from('<HHII',d,e)
    sz={1:1,2:1,3:2,4:4,5:8,7:1,9:4,10:8,11:4,12:8}[k]*n;o=e+8 if sz<=4 else v
    if k in (3,4):tags[t]=struct.unpack_from('<%d%s'%(n,'H' if k==3 else 'I'),d,o)
    elif k==5:tags[t]=[a/b for a,b in [struct.unpack_from('<II',d,o+8*j) for j in range(n)]]
    else:tags[t]=list(d[o:o+sz])
w,h=tags[256][0],tags[257][0];assert tags[258]==(12,) and tags[259]==(1,)
offset,count=tags[273][0],tags[279][0];expected=w*h*3//2
assert expected<=count<=expected+15 and offset+count<=len(d)
print(json.dumps({'strip_bytes':count,'raster_bytes':expected,'trailing_bytes_hex':d[offset+expected:offset+count].hex()}))
raw=d[offset:offset+expected];pixels=[]
for y in range(h):
    row=[]
    for x in range(0,w//2*3,3):
        a,b,c=raw[y*w//2*3+x:y*w//2*3+x+3];row.extend(((a<<4)|(b>>4),((b&15)<<8)|c))
    pixels.append(row)
vals=sorted(v for row in pixels[::8] for v in row[::8]);black=sum(tags.get(50714,[0]))/len(tags.get(50714,[0]))
white=vals[int(len(vals)*.995)];asn=tags.get(50728,[1,1,1]);gains=[1/v for v in asn];gains=[g/gains[1] for g in gains]
encoded=bytearray()
for y in range(0,h,2):
    encoded.append(0)
    for x in range(0,w,2):
        values=(pixels[y][x],(pixels[y][x+1]+pixels[y+1][x])/2,pixels[y+1][x+1])
        for v,k in zip(values,gains):encoded.append(round(max(0,min(1,(v-black)*k/max(1,white-black)))**(1/2.2)*255))
def chunk(t,v):return struct.pack('>I',len(v))+t+v+struct.pack('>I',zlib.crc32(t+v))
assert not out.exists(),out
out.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w//2,h//2,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(encoded))+chunk(b'IEND',b''))
print(json.dumps({'source':str(path),'raster':[w,h],'black':black,'white':white,'preview':str(out)}))
