"""Hex-dump records of a set that contain a BE pool offset of a given string. usage: set string..."""
import sys, struct
sys.path.insert(0,'/Users/dido/Developer.localized/SIGMAfp_re/research/ui/tools/nbu_probe')
import nbu_format as N
img,base,rows,(pb,ps)=N.load_sets(); pool=img[pb-base:pb-base+ps]
setname=sys.argv[1]; offs=[pool.find(b'\0'+s.encode()+b'\0')+1 for s in sys.argv[2:]]
row=next(r for r in rows if r['name']==setname)
for r in N.split(img[row['address']-base:]):
    b=r.body
    for o in offs:
        if struct.pack('>I',o) in b:
            print(hex(r.tag),len(b),b.hex(' ',4))
            # print strings at every 4-byte window (unaligned too)
            for i in range(len(b)-3):
                w=struct.unpack_from('>I',b,i)[0]
                if 0<w<len(pool) and pool[w-1]==0 and pool[w]!=0: print('   @%d'%i, repr(pool[w:pool.index(b'\0',w)][:50].decode('latin1')))
