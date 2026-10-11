"""Build length-preserving native UI edits; does not install them.

New animation keys borrow serialized space from redundant constant keys.
QS limits borrow four bytes from an explicit default-white image property.
Every relocated region remains inside one screen, with unchanged endpoints.
"""
import struct, json, hashlib
from pathlib import Path
from inspect_uic_resources import load, POOL, START

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'prototype/development/native-ui'
U32=lambda b,o=0:struct.unpack_from('>I',b,o)[0]
def word(b,o,v):struct.pack_into('>I',b,o,v)

def animation(data):
    if U32(data)!=0x1000a:return None
    count=U32(data,12);p=28;properties=[]
    for _ in range(count):
        if p+20>len(data):return None
        n,typ,component,name,dimension=struct.unpack_from('>5I',data,p)
        if typ not in (0,1,2) or not 0<n<10000 or p+20+10*n>len(data):return None
        keys=[bytes(data[p+20+i*10:p+30+i*10]) for i in range(n)]
        properties.append([typ,component,name,dimension,keys]);p+=20+10*n
    return properties if p==len(data) else None

def encode_animation(original,properties):
    out=bytearray(original[:28]);word(out,12,len(properties))
    for typ,component,name,dimension,keys in properties:
        out.extend(struct.pack('>5I',len(keys),typ,component,name,dimension))
        out.extend(b''.join(keys))
    word(out,4,len(out));return out

def build():
    main,strings,index=load();lookup={v:k for k,v in strings.items()}
    records=[];screen=0
    for address,size,tag in index:
        if tag==0x10002:screen=address
        records.append(dict(address=address,size=size,tag=tag,screen=screen,data=bytearray(main[address:address+size])))
    # Short internal names fit entirely inside existing three-byte alignment pads.
    aliases={};pool_patches=[]
    for name in ['3L','3M','3Q','3S']:
        assert name not in lookup
        for offset,value in strings.items():
            end=POOL+offset+len(value.encode())+1
            if end%4==1 and end<START-3 and all(end!=p['address'] for p in pool_patches):
                assert main[end:end+3]==bytes(3)
                aliases[name]=end-POOL
                pool_patches.append(dict(address=end,old=bytes(3),new=name.encode()+b'\0'))
                break
        else:raise AssertionError('No isolated string padding available')
    groups=[];changes=[];modified=set()
    def reserve(i,needed):
        lo=hi=i
        # Reduce equal-valued numeric/string keys, retaining the final time.
        candidates=sorted(range(len(records)),key=lambda j:abs(records[j]['address']-records[i]['address']))
        for j in candidates:
            r=records[j]
            if r['screen']!=records[i]['screen'] or abs(r['address']-records[i]['address'])>8192:continue
            if needed<10:break
            props=animation(r['data'])
            if props is None:continue
            saved=0
            for prop in props:
                keys=prop[4]
                while needed>=10 and len(keys)>1 and len({k[6:] for k in keys})==1:
                    keys.pop(0);needed-=10;saved+=10
            if saved:
                r['data']=encode_animation(r['data'],props);modified.add(j)
                changes.append(dict(kind='constant-key-space',address=hex(0xc0000000+r['address']),bytes=saved))
                lo=min(lo,j);hi=max(hi,j)
            if needed==0:break
        if needed==4:
            for j in candidates:
                r=records[j];d=r['data']
                if r['screen']!=records[i]['screen'] or abs(r['address']-records[i]['address'])>8192:continue
                # Stock drawImage: image, white color, rect. The common 0x81
                # form already relies on the native default-white color.
                if r['tag']==0x10005 and len(d)==56 and U32(d,8)==lookup['drawImage'] and U32(d,28)==0x85 and U32(d,36)==0xffffffff:
                    del d[36:40];word(d,4,52);word(d,28,0x81);needed=0
                    modified.add(j);lo=min(lo,j);hi=max(hi,j)
                    changes.append(dict(kind='default-white-space',address=hex(0xc0000000+r['address']),bytes=4));break
        assert needed==0,('No equivalent space donor',hex(records[i]['address']),needed)
        groups.append((lo,hi))
    targets=[]
    for i,r in enumerate(records):
        props=animation(r['data'])
        if props is None:continue
        for prop in props:
            typ,component,name,dimension,keys=prop
            if typ!=2 or strings.get(name)!='image':continue
            names=[strings.get(U32(k,6)) for k in keys]
            mapping={('L_resolution_1','L_resolution_2'):('3L',2),
                     ('M_resolution_1','M_resolution_2'):('3M',2),
                     ('qs_resolution_1_S','qs_resolution_2_S'):('3Q',2),
                     ('set_resolution_1','set_resolution_2'):('3S',2),
                     ('L_resolution_1','L_resolution_2','L_resolution_dci4K'):('3L',3),
                     ('M_resolution_1','M_resolution_2','M_resolution_dci4K'):('3M',3)}
            if tuple(names) not in mapping:continue
            alias,private=mapping[tuple(names)]
            assert [struct.unpack_from('>H',k,4)[0] for k in keys]==list(range(0,len(keys)*33,33))
            keys.append(struct.pack('>IHI',0,private*33,aliases[alias]))
            r['data']=encode_animation(r['data'],props);modified.add(i)
            targets.append(dict(address=hex(0xc0000000+r['address']),stock=names,alias=alias,private_index=private))
            reserve(i,10)
            break
    for address in [0xc237249f,0xc25e405a]:
        i=next(i for i,r in enumerate(records) if r['address']==address-0xc0000000)
        d=records[i]['data']
        assert len(d)==40 and U32(d,8)==lookup['controlValue'] and U32(d,28)==0x18
        d[32:32]=struct.pack('>f',2.0);word(d,4,44);word(d,28,0x1a);modified.add(i)
        changes.append(dict(kind='QS-resolution-maximum',address=hex(address),maximum=2))
        reserve(i,4)
    # Overlapping relocation regions must be written and validated together.
    merged=[]
    for lo,hi in sorted(groups):
        if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
        else:merged.append((lo,hi))
    patches=list(pool_patches)
    for lo,hi in merged:
        start=records[lo]['address'];end=records[hi]['address']+records[hi]['size']
        assert records[lo]['screen']==records[hi]['screen']
        data=b''.join(bytes(r['data']) for r in records[lo:hi+1])
        assert len(data)==end-start,(hex(start),len(data),end-start)
        patches.append(dict(address=start,old=main[start:end],new=data))
    assert all(any(lo<=i<=hi for lo,hi in merged) for i in modified)
    # Record stream remains structurally valid and each screen boundary fixed.
    candidate=bytearray(main)
    for p in patches:candidate[p['address']:p['address']+len(p['old'])]=p['new']
    p=index[0][0];ends={r['address'] for r in records if r['tag']==0x10002};seen=set()
    while p<index[-1][0]+index[-1][1]:
        tag,size=struct.unpack_from('>II',candidate,p);assert size>=8
        if tag==0x10002:seen.add(p)
        p+=size
    assert seen==ends and p==index[-1][0]+index[-1][1]
    report=dict(status='Offline candidate; native animation playback not yet verified',aliases=aliases,targets=targets,changes=changes,
                patches=[dict(address=hex(0xc0000000+x['address']),old=x['old'].hex(),new=x['new'].hex()) for x in patches],
                changed_regions=len(patches),serialized_bytes=sum(len(x['old'])+len(x['new']) for x in patches))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'ui-resource-plan.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['targets','patches','changes']},indent=2))
    print('Resolution animations:',len(targets))
    return report

if __name__=='__main__':build()
