"""Find NBU records (any set) whose body contains a BE word == pool offset of the given strings."""
import sys, struct
sys.path.insert(0,'/Users/dido/Developer.localized/SIGMAfp_re/research/ui/tools/nbu_probe')
import nbu_format as N
img,base,rows,(pb,ps)=N.load_sets()
pool=img[pb-base:pb-base+ps]
def off(s):
    i=pool.find(b'\0'+s.encode()+b'\0'); return i+1
def s_at(o):
    if 0<=o<len(pool): return pool[o:pool.index(b'\0',o)].decode('latin1')
targets={off(s):s for s in sys.argv[1:]}
print({hex(k):v for k,v in targets.items()})
def walk(recs,setname,depth=0):
    for r in recs:
        body=r.body if hasattr(r,'body') else None
        if body is None: continue
        for i in range(0,len(body)-3,4):
            w=struct.unpack_from('>I',body,i)[0]
            if w in targets:
                ws=struct.unpack_from('>%dI'%min(12,len(body)//4),body,0)
                print(setname,hex(r.tag),'len',len(body),'@',i,targets[w],'|',[s_at(x) if 4<=x<len(pool) and pool[x-1]==0 else hex(x) for x in ws])
for row in rows:
    try: recs=N.split(img[row['address']-base:])
    except Exception as e: continue
    walk(recs,row['name'])
