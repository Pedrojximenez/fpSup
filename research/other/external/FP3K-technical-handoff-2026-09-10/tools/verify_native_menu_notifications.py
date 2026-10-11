"""Execute stock notification routing using v2 context and constructor-derived observers.
UI endpoints and exclusion evaluation are mocked, not the dispatcher/observer adapters.
"""
from pathlib import Path
import hashlib, json, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR
ROOT = Path(__file__).resolve().parents[1]
firmware = (ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest() == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
snapshot = (ROOT/'diagnostics/menu-native-v2-return/SSD/FP3KM2/SERVICE2.BIN').read_bytes()
assert struct.unpack_from('<II', snapshot, 0x24) == (0xc3765e14, 0xc3762bf0)
cases = []
for enabled, value in [(True, 3), (True, 2), (False, 3)]:
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    size = (len(firmware)+4095)&~4095
    u.mem_map(0xc0000000, size)
    u.mem_write(0xc0000000, firmware)
    u.mem_protect(0xc0000000, size, UC_PROT_READ | UC_PROT_EXEC)
    for page in (0xc31ac000, 0xc3762000, 0xc3765000):
        u.mem_map(page, 4096)
    u.mem_map(0x10000000, 0x10000)
    def put(address, *words):
        u.mem_write(address, struct.pack('<'+'I'*len(words), *words))
    u.mem_write(0xc31ac51c, snapshot)
    u.mem_write(0xc31ac56c, bytes([enabled]))
    put(0xc3765e14, 0xc0cd9324)
    put(0xc3762bf0, 0xc0cbee94, 0xc3762bd8)
    put(0xc3762be0, 0xc0cccd44)
    put(0xc3762be8, 0x10000100)
    put(0x10000100, 0x10000200)
    put(0x10000200, 0x10000300)
    put(0x10000314, 0x10001000)  # UI interface getter
    put(0x10000400, 0x10000500)
    put(0x100005f4, 0x10001004)  # resolution display endpoint
    put(0x10000600, 0x69, 0)
    seen = []
    def hook(uc, address, length, data):
        r0, r1 = (uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1))
        if address == 0xc049ec58:
            result = 0x10000800
        elif address == 0xc049ed70:
            assert r1 == 0x69
            seen.append(['exclusion_rules', r1])
            result = 0
        elif address == 0xc0057ae8:
            result = 0xc31ac530
        elif address == 0xc005c058:
            result = value
        elif address == 0x10001000:
            result = 0x10000400
        elif address == 0x10001004:
            assert r0 == 0x10000400
            seen.append(['resolution_display', r1])
            result = 0
        else:
            raise AssertionError(hex(address))
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    for address in (0xc049ec58, 0xc049ed70, 0xc0057ae8, 0xc005c058, 0x10001000, 0x10001004):
        u.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)
    u.reg_write(UC_ARM_REG_R0, 0xc31ac540)
    u.reg_write(UC_ARM_REG_R1, 0x10000600)
    u.reg_write(UC_ARM_REG_SP, 0x1000fff0)
    u.reg_write(UC_ARM_REG_LR, 0xc0000000)
    u.emu_start(0xc0090e38, 0xc0000000, count=10000)
    assert u.reg_read(UC_ARM_REG_PC) == 0xc0000000
    assert seen == ([['exclusion_rules', 105], ['resolution_display', value]] if enabled else [])
    assert bytes(u.mem_read(0xc31ac540, 40)) == snapshot[0x24:0x4c]
    cases.append(dict(enabled=enabled, resolution=value, calls=seen, subscribers_retained=True, passed=True))
report = dict(cases=cases, capture='menu-native-v2/SERVICE2', limitations='Observer vtables/owner reconstructed from stock constructors; UI interface, resolution getter, and exclusion evaluation mocked. Does not prove sensor restart, UI rendering, or safe live mode switching.')
(ROOT/'analysis/firmware/menu-integration/native-notification-verification.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
