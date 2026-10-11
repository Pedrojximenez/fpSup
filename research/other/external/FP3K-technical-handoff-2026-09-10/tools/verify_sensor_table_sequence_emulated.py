"""Capture stock sensor-programming requests in an emulator, with mocked I/O.

This does NOT emulate a sensor, receiver, delays or mode-transition timing.
"""
import hashlib
import json
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/firmware'
b = (OUT/'MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest() == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
n = (len(b)+4095)&~4095
u.mem_map(0xc0000000,n)
u.mem_write(0xc0000000,b)
u.mem_protect(0xc0000000,n,UC_PROT_READ|UC_PROT_EXEC)
OBJ,STACK,STATE,STOP = 0x10000000,0x10010000,0xc2f1e7b0,0xc0000000
u.mem_map(OBJ,4096)
u.mem_map(STACK,0x4000)
u.mem_map(STATE&~4095,4096)
u.mem_write(OBJ,struct.pack('<I',0xc0b5fda4))
requests=[]
def io(uc,address,size,data):
    if address == 0xc0322c70:
        requests.append([uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)])
    uc.reg_write(UC_ARM_REG_R0,0)
    uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
for address in (0xc0322c70,0xc0125030,0xc0125058):
    u.hook_add(UC_HOOK_CODE,io,begin=address,end=address)
def guard(uc,access,a,n,v,data):
    assert (STACK<=a and a+n<=STACK+0x4000) or (STATE<=a and a+n<=STATE+4),hex(a)
u.hook_add(UC_HOOK_MEM_WRITE,guard)
table=json.loads((OUT/'sensor-registers.json').read_text())
rows={r['mode_id']:r for r in table['rows']}
cases=[]
for mode in (3,121,151,98,106,218,11,8):
    for initial in (0,0x2fffa):
        requests.clear()
        u.mem_write(STATE,struct.pack('<I',initial))
        u.reg_write(UC_ARM_REG_R0,OBJ)
        u.reg_write(UC_ARM_REG_R1,mode)
        u.reg_write(UC_ARM_REG_SP,STACK+0x3ff0)
        u.reg_write(UC_ARM_REG_LR,STOP)
        u.emu_start(0xc03258c8,STOP,count=20000)
        assert u.reg_read(UC_ARM_REG_PC)==STOP
        expected=[[m['register'],rows[mode]['words'][m['word_index']]] for m in table['mapping']]
        value=0x2fffb if initial==0x2fffa else 0x2fffa
        expected += [[0xce,0],[0xd1,value&255],[0xd2,(value>>8)&255],[0xd3,(value>>16)&255]]
        assert requests==expected,(mode,initial)
        assert struct.unpack('<I',u.mem_read(STATE,4))[0]==value
        cases.append(dict(mode=mode,initial_toggle=initial,final_toggle=value,
                          write_count=len(requests),tail=requests[-4:]))
capture=(ROOT/'diagnostics/v003-uhd24-retry/SSD/FPD003/STATE.BIN').read_bytes()
assert hashlib.sha256(capture).hexdigest()=='6c10b388be9b5c2695b627b7524ccc57fbd60bb4f02953e5e6d4a74f970838e7'
override_values=sorted({capture[64+i*832+0x20+0x58] for i in range(120)})
assert override_values==[0]
comparisons=[]
for a,c in [(151,3),(151,121),(218,98),(218,11),(218,8)]:
    differences=[dict(register=hex(m['register']),a=rows[a]['words'][m['word_index']],b=rows[c]['words'][m['word_index']])
                 for m in table['mapping'] if rows[a]['words'][m['word_index']]!=rows[c]['words'][m['word_index']]]
    comparisons.append(dict(modes=[a,c],differences=differences))
report=dict(cases=cases,entry='0xc03258c8',table_comparisons=comparisons,
    baseline_override_enable_values=override_values,
    baseline_override_caveat='Zero in all120 snapshots, including recording; snapshots do not cover every instruction of a mode transition.',
    mocked_functions=['0xc0322c70 sensor-register I/O','0xc0125030','0xc0125058'],
    conclusion='All161 table-fed writes plus four trailing writes match. The trailing CE/D1/D2/D3 values depend on a fixed software toggle, not the mode ID.',
    limitations='No sensor or receiver modeled. C03234A0 optional per-mode override writes and other timing/exposure setup are excluded. This is not a complete mode-switch trace.')
(OUT/'sensor-table-sequence-emulation.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'PASS: {len(cases)} cases,165 register requests each; sensor I/O mocked.')
