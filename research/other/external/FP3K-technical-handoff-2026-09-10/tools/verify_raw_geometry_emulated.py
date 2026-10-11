"""Execute stock RAW descriptor and path-selection routines offline, without camera access."""
from pathlib import Path
import json,struct,hashlib
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_PROT_READ,UC_PROT_EXEC,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'analysis/firmware'
b=(OUT/'MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0xc0000000,(len(b)+4095)&~4095);u.mem_write(0xc0000000,b);u.mem_protect(0xc0000000,(len(b)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
BASE=0x10000000;STACK=0x10010000;STOP=0xc0000000
u.mem_map(BASE,0x4000);u.mem_map(STACK,0x4000)
allowed=[]
def guard(uc,access,a,n,v,data):assert any(lo<=a and a+n<=hi for lo,hi in allowed),hex(a)
u.hook_add(UC_HOOK_MEM_WRITE,guard)
def run(a,*args,writes):
 allowed[:]=[(STACK,STACK+0x4000),*writes];u.reg_write(UC_ARM_REG_SP,STACK+0x3ff0);u.reg_write(UC_ARM_REG_LR,STOP)
 for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,v)
 u.emu_start(a,STOP,count=20000)
 assert u.reg_read(UC_ARM_REG_PC)==STOP
 return u.reg_read(UC_ARM_REG_R0)
def put(a,ws):u.mem_write(a,struct.pack('<'+'I'*len(ws),*ws))
def get(a,n):return list(struct.unpack('<'+'I'*n,u.mem_read(a,4*n)))
profiles=json.loads((OUT/'raw-profiles.json').read_text());row=next(r for r in profiles['rows'] if 429 in r['profile_ids'])
PARAM,SOURCE,DESC,CTX,INPUT,RESULT=[BASE+i for i in (0x100,0x300,0x600,0x800,0x900,0xa00)]
cases=[]
for name,changes in [('stock429',{}),('geometry_only_3032x2020',{0xdc:3032,0xe4:2020,0x24:3000,0x2c:2000}),('geometry_and_zoom2048',{0xdc:3032,0xe4:2020,0x24:3000,0x2c:2000,0x64:2048,0xd4:2048})]:
 p=row['words']+[6064,4042]
 for off,value in changes.items():p[off//4]=value
 put(PARAM,p);u.mem_write(SOURCE,bytes(0x60));put(SOURCE,[429,PARAM]);put(SOURCE+0x58,[0xc0bd04b0]);put(CTX,[0,0]);u.mem_write(DESC,bytes(0xc0))
 run(0xc0438018,DESC,SOURCE,CTX,writes=[(DESC,DESC+0xc0)])
 d=get(DESC,48)
 # Exactly the two 7-word input groups constructed at C031D9D0..C031DB00.
 raw=[d[0],d[1],max(d[18],1024),max(d[19],1024),(1,3,5)[d[20]],(1,3)[d[21]],d[8]]
 prev=[d[22],d[23],max(d[40],1024),max(d[41],1024),(1,3,5)[d[42]],(1,3)[d[43]],d[30]]
 put(INPUT,raw+prev)
 initial=bytearray(0x4c)
 for off,value in {4:1,8:1,12:1,16:1,24:1,28:2,36:1,40:1,44:1,48:1,52:1024,56:1024,60:1024,64:1024}.items():struct.pack_into('<I',initial,off,value)
 u.mem_write(RESULT,bytes(initial));run(0xc0325228,0,INPUT,RESULT,writes=[(RESULT,RESULT+0x4c)])
 out=bytes(u.mem_read(RESULT,0x4c))
 cases.append({'case':name,'hypothetical':bool(changes),'parameter_changes':{hex(k):v for k,v in changes.items()},'descriptor_words':d,'raw_input':raw,'preview_input':prev,'path_enable_bytes':list(out[:3]),'output_words':get(RESULT,19)})
assert cases[0]['raw_input'][:4]==[3856,2170,1600,1600]
assert cases[1]['descriptor_words'][:2]==[3032,2020]
assert cases[2]['raw_input'][2:4]==[2048,2048]
r={'cases':cases,'validated':'Stock descriptor construction and pure path selection executed, with firmware read/execute and destination/stack write guards. No firmware routines stubbed.','limitations':'Hypothetical inputs are not patches. Sensor timing, MMIO, filters, allocator/DMA, DNG writer and image quality are not emulated.'}
(OUT/'raw-geometry-emulation.json').write_text(json.dumps(r,indent=2)+'\n')
for c in cases:print(c['case'],'raw',c['raw_input'],'preview',c['preview_input'],'paths',c['path_enable_bytes'],'ratios',c['output_words'][13:17])
# Emulate only the pure register-programming routine against ordinary RAM.
# This proves values written, not peripheral behavior, DMA or allocation safety.
u.mem_map(0x30182000,0x1000)
packing=[]
for width in (3856,3032,3000,6064):
 u.mem_write(0x30182000,bytes(0x1000))
 run(0xc0630e91,width,0,writes=[(0x30182000,0x30183000)])
 regs=get(0x3018220c,5)
 assert regs[2]==width*3//8
 packing.append({'width':width,'format':0,'transfer_units':regs[2],'bytes_if_32bit_units':regs[2]*4,'chunk_units':regs[3],'registers':[hex(v) for v in regs]})
r['packing_register_tests']=packing
r['geometry_arithmetic']=[]
for label,sw,sh,ow,oh,zoom in [('stock',6064,3412,3856,2170,1600),('fullheight_dimensions_only',6064,4042,3032,2020,1600),('fullheight_half',6064,4042,3032,2020,2048)]:
 reduced=[(sw*1024+zoom//2)//zoom,(sh*1024+zoom//2)//zoom]
 offsets=[((a-b)//4)*2 if a>b else 0 for a,b in zip(reduced,[ow,oh])]
 r['geometry_arithmetic'].append({'case':label,'reduced_extent':reduced,'raw_raster':[ow,oh],'even_center_offset':offsets,'packed_12bit_bytes':ow*oh*3//2})
(OUT/'raw-geometry-emulation.json').write_text(json.dumps(r,indent=2)+'\n')
print('Packing:',packing)
print('Geometry:',r['geometry_arithmetic'])
