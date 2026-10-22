"""Extract the two LZSS sections in the supplied Sigma fp 5.02 update.
Read-only input; no patching, repacking, installation, or camera access.
Pinned to one verified source image, not a general firmware-format parser.
"""
from pathlib import Path
import argparse,struct,hashlib,json
SOURCE_SHA='c9fa76f32f523bb2dc9a3fbda39418c31573cab6a1aa5c56d28c371862066ed8'

def decompress(src, expected):
 ring=bytearray(4096); r=0xfee; out=bytearray(); p=0; extra=[]
 while len(out)<expected:
  if p>=len(src):raise ValueError('truncated flag')
  flags=src[p];p+=1
  for bit in range(8):
   if len(out)==expected:break
   if flags & (1<<bit):
    if p>=len(src):raise ValueError('truncated literal')
    val=src[p];p+=1;out.append(val);ring[r]=val;r=(r+1)&4095
   else:
    if p+2>len(src):raise ValueError('truncated match')
    lo,hi=src[p:p+2];p+=2;off=lo|((hi&0xf0)<<4);n=(hi&15)+3
    for k in range(n):
     val=ring[(off+k)&4095];ring[r]=val;r=(r+1)&4095
     if len(out)<expected:out.append(val)
     else:extra.append(val)
 # Stop at the header's output bound. Preserve the overshoot as evidence;
 # do not interpret compressed sector padding as executable data.
 return bytes(out),p,bytes(extra).hex()

def extract(path,dest):
 b=path.read_bytes();sha=hashlib.sha256(b).hexdigest()
 if sha!=SOURCE_SHA:raise ValueError('Unrecognized firmware; extractor is pinned to the supplied V5.02 image')
 if b[0x100:0x104]!=b'@DFI':raise ValueError('DFI marker mismatch')
 info={'source_sha256':sha,'source_size':len(b),'segments':[]}
 for name,hdr in [('MAIN',0x120),('DAT1',0x138)]:
  size,off,base,csum,flags,packed=struct.unpack_from('<6I',b,hdr)
  start=0x300+off;src=b[start:start+packed]
  if len(src)!=packed or sum(src)&0xffffffff!=csum:raise ValueError('compressed section checksum mismatch')
  out,used,extra=decompress(src,size)
  dest.mkdir(parents=True,exist_ok=True);fn=f'{name}_{base:08x}.bin';(dest/fn).write_bytes(out)
  info['segments'].append(dict(name=name,file=fn,header_offset=hdr,load_address=base,uncompressed_size=size,compressed_offset=start,compressed_size=packed,compressed_consumed=used,final_match_bytes_beyond_size_hex=extra,compressed_byte_sum=csum,checksum_verified=True,sha256=hashlib.sha256(out).hexdigest()))
 main=(dest/'MAIN_c0000000.bin').read_bytes()
 checks={0:bytes.fromhex('18f09fe5'),0xbac2f8:bytes.fromhex('a0993dc0'),0xd0794:bytes.fromhex('d76f04fa'),0xcf3740:bytes.fromhex('03060101')}
 if any(main[a:a+len(v)]!=v for a,v in checks.items()):raise ValueError('upstream address cross-check failed')
 info['upstream_address_cross_checks']={hex(0xc0000000+a):v.hex() for a,v in checks.items()}
 (dest/'extraction.json').write_text(json.dumps(info,indent=2)+'\n');return info

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('firmware',type=Path);ap.add_argument('--output',type=Path,default=Path('analysis/firmware'));a=ap.parse_args();print(json.dumps(extract(a.firmware,a.output),indent=2))
