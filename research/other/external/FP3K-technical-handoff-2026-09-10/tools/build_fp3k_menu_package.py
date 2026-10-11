"""Build integrated native-menu demo package, without writing removable media."""
import hashlib,json,struct,sys
from pathlib import Path
from build_fp3k_native_menu import build as resident_build,ROOT,BASE,STATE,HOOKS,branch_word
sys.path.insert(0,str(ROOT/'research/fpSup/fp_usb_shell'))
from armasm import assemble
BOOT=0xc0732100;BOOT_STATE=0xc0732500
OUT=ROOT/'prototype/fp3k-0.3.5-preview3'
def build():
 payload,syms,entries,main,resident=resident_build()
 (ROOT/'tools/fp3k_menu_boot_data.inc').write_text(f'.equ LENGTH, {len(payload)}\n')
 rows=[f'.equ BOOT_HOOK_COUNT, {len(HOOKS)}','boot_hooks:']
 for a,label in HOOKS:
  old=struct.unpack_from('<I',main,a-0xc0000000)[0]
  new=branch_word(a,BASE+syms[label],label)
  rows.append(f'.word 0x{a:08x}, 0x{old:08x}, 0x{new:08x}')
 (ROOT/'tools/fp3k_menu_boot_hooks.inc').write_text('\n'.join(rows)+'\n')
 loader=assemble(ROOT/'tools/fp3k_menu_boot.S')
 assert BOOT+len(loader)<BOOT_STATE
 assert main[BOOT-0xc0000000:BOOT_STATE-0xc0000000+16]==bytes(BOOT_STATE-BOOT+16)
 lines=['# FP3K 0.3.5 preview display-fit experiment; Sigma fp 5.02 only.']
 lines += [f'mem set 0x{BOOT+4*i:08X} 0x{v:08X}' for i,v in enumerate(struct.unpack('<'+'I'*(len(loader)//4),loader))]
 lines += [f'mem set 0xC0BAC2F8 0x{BOOT:08X}','echo','mem set 0xC0BAC2F8 0xC03D99A0']
 lines += ['mem save \\FP3KM2\\RANGE.BIN 0xC1A7099C,,40']
 lines += [f'mem save \\FP3KM2\\BOOT.BIN 0x{BOOT_STATE:08X},,16', f'mem save \\FP3KM2\\MENU.BIN 0x{STATE:08X},,64', 'mem save \\FP3KM2\\LIST.BIN 0xC0F8E7EC,,89', f'mem save \\FP3KM2\\CODE.BIN 0x{BASE:08X},,{len(payload)}']
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/'FP3KM2').mkdir(exist_ok=True)
 for device in ['SD','SSD']:(ROOT/'diagnostics/native-menu-demo-return'/device/'FP3KM2').mkdir(parents=True,exist_ok=True)
 (ROOT/'diagnostics/native-menu-demo-return/clips').mkdir(exist_ok=True)
 for name,data in [('AutoRun.txt',('\r\n'.join(lines)+'\r\n').encode()),('FP3KMENU.BIN',payload),('loader.bin',loader)]: (OUT/name).write_bytes(data)
 manifest=dict(version='0.3.5-preview3',status='Integrated experimental candidate; camera validation pending; not installed',firmware='Sigma fp 5.02',explicit_sleep_ms=0,commands=len(lines)-1,bootstrap_address=hex(BOOT),bootstrap_status=hex(BOOT_STATE),resident=resident,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [OUT/'AutoRun.txt',OUT/'FP3KMENU.BIN',OUT/'loader.bin']},limitations=['No timed startup delay; actual camera startup timing remains unmeasured.','Native resource caching, UI rendering and live selection behavior require the integrated camera demo.','Select another resolution before leaving CINE or removing SSD; physical switches/removal and preset paths are not all intercepted.','Unsupported settings reject 3K selection; dynamic greying is not implemented.'])
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return loader,payload,manifest
if __name__=='__main__':print(json.dumps(build()[2],indent=2))
