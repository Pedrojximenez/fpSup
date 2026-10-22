"""Execute stock Thumb CSV parser on both resolution-list resources."""
import json,struct
from unicorn import *
from unicorn.arm_const import *
from native_resolution_resource import stock,CSV,ROOT
b,original=stock();results=[]
for label,data in [('stock',original),('three-choice',CSV)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);n=(len(b)+4095)&~4095
 u.mem_map(0xc0000000,n);u.mem_write(0xc0000000,b);u.mem_protect(0xc0000000,n,UC_PROT_READ|UC_PROT_EXEC)
 u.mem_map(0x10000000,0x20000)
 def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 model=0x10000100;alloc=0x10000200;source=0x10000300
 put(model,alloc);put(alloc,0x10001000,0x10001004)
 put(source,len(data),0x10000400);u.mem_write(0x10000400,data)
 heap=[0x10002000];allocations=[]
 def allocation(uc,a,n,d):
  length=uc.reg_read(UC_ARM_REG_R0)
  assert 0<length<4096
  result=heap[0];heap[0]+=(length+7)&~7;assert heap[0]<0x10008000
  allocations.append((result,length))
  uc.reg_write(UC_ARM_REG_R0,result);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,allocation,begin=0x10001000,end=0x10001000)
 def guard(uc,access,a,n,v,d):
  assert model<=a and a+n<=model+0x28 or a==0x10000500 or 0x10010000<=a and a+n<=0x10020000 or any(p<=a and a+n<=p+l for p,l in allocations),hex(a)
 u.hook_add(UC_HOOK_MEM_WRITE,guard)
 u.reg_write(UC_ARM_REG_R0,model);u.reg_write(UC_ARM_REG_R1,source);u.reg_write(UC_ARM_REG_R2,0x10000500)
 u.reg_write(UC_ARM_REG_SP,0x1001fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
 u.emu_start(0xc05f57c9,0xc0000000,count=100000)
 assert u.reg_read(UC_ARM_REG_PC)==0xc0000000 and u.reg_read(UC_ARM_REG_R0)==0
 assert get(0x10000500)==0
 count,cols=get(model+0x14),get(model+0x18)
 def string(a):return bytes(u.mem_read(a,100)).split(b'\0',1)[0].decode()
 headers=[string(get(get(model+0x24)+4*i)) for i in range(cols)]
 rows=[[string(get(get(model+0x20)+4*(j*cols+i))) for i in range(cols)] for j in range(count)]
 assert count==(2 if label=='stock' else 3)
 parsed=[dict(zip(headers,r)) for r in rows]
 for i in range(2):assert all(parsed[i][k]==v for k,v in {'NO':str(i+1),'TEXT':str(313+i).zfill(4),'IMAGE':'blank','Enabled':'1','Enabled2':'2'}.items())
 if label!='stock':assert parsed[2]=={'NO':'3','TEXT':'3K 3000x2000','IMAGE':'','Enabled':'1','Enabled2':'2'}
 results.append(dict(case=label,columns=headers,rows=parsed,passed=True))
report=dict(cases=results,native_parser='0xc05f57c8',mocked=['bounded allocator'],limitations='Parsing verified, not native rendering or safe capture activation. Popup column removal must match the specific list bindings.')
out=ROOT/'prototype/development/native-menu';out.mkdir(parents=True,exist_ok=True)
(out/'csv-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
