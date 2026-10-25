"""Offline RT5035C current-control analysis and original ARM execution.

This module has no host transport. I2C callbacks below only update a dictionary.
"""
import struct

from firmware import Firmware

DATASHEET = "https://www.richtek.com/assets/product_file/RT5035C=RT5035D/DS5035CD-01.pdf"
INIT_TABLES = (0xC072C73C, 0xC072C7A4)
INIT_SIZE = 13 * 8
INIT, SET_DIM, ENABLE = 0xC0042798, 0xC00429C8, 0xC0042A58
POWER_TEST_INIT, LCD_ENABLE_CALLBACK = 0xC0042F30, 0xC0308520
RANGES = ((INIT, 0xC0042870), (SET_DIM, ENABLE), (ENABLE, 0xC0042AE8),
          (0xC0042CB0, 0xC0042D70), (POWER_TEST_INIT, 0xC0042FA0),
          (LCD_ENABLE_CALLBACK, 0xC0308578))


def init_entries(firmware, base):
    if base not in INIT_TABLES:
        raise ValueError("unsupported PMIC init table")
    return [struct.unpack("<II", firmware.read(base + i * 8, 8)) for i in range(13)]


def current_ratio(dim):
    if not isinstance(dim, int) or isinstance(dim, bool) or not 0 <= dim <= 31:
        raise ValueError("DIM7 must be an integer in 0..31")
    return (dim + 1) / 32


def make_current_plan(firmware, dim):
    current_ratio(dim)
    if dim <= 18:
        raise ValueError("this experiment only describes candidates above stock init 18")
    guards = []
    for base in INIT_TABLES:
        entries = init_entries(firmware, base)
        if entries[3] != (4, 0xB2):
            raise ValueError("PMIC init current/voltage identity changed")
        before = firmware.read(base, INIT_SIZE)
        after = bytearray(before)
        struct.pack_into("<I", after, 3 * 8 + 4, 0xA0 | dim)
        guards.append({"address": hex(base), "size": INIT_SIZE,
                       "before_hex": before.hex(), "after_hex": bytes(after).hex(),
                       "value_address": hex(base + 3 * 8 + 4)})
    return {
        "schema": "fp-backlight-current-offline-plan-v1",
        "status": "offline_experiment_not_hardware_validated",
        "firmware": firmware.identity,
        "dim7": dim, "stock_init_dim7": 18,
        "register": 4, "register_before": 0xB2, "register_after": 0xA0 | dim,
        "current_fraction_of_resistor_defined_full_scale": current_ratio(dim),
        "current_ratio_to_stock_init": (dim + 1) / 19,
        "current_gain_percent_to_stock_init": ((dim + 1) / 19 - 1) * 100,
        "measured_nits": None, "nits_gain_percent": None,
        "guards": guards,
        "source": {"url": DATASHEET, "pages": [21, 28, 32]},
        "scope": "local image/table experiment only; no card, native call or device write",
        "limitations": [
            "Stock 18 is proven for both normal init tables, not a live register measurement.",
            "The native power-test initialization can separately set 31.",
            "CH7 wiring is inferred from the LCD power callback and EN7 register definition.",
            "LED current ratio is not a measured luminance ratio.",
            "Actual current requires the camera's unknown FB7 external sense resistance.",
            "Panel/LED ratings, power, temperature, and long-term suitability are unverified.",
            "VOUT8 upper bits, OVP, enables and all other init entries are preserved.",
        ],
    }


def guarded_init_table(current, firmware, plan, base, *, restore=False):
    if plan.get("schema") != "fp-backlight-current-offline-plan-v1":
        raise ValueError("unknown current plan")
    # Rebuild from exact supported firmware; reject a forged or widened plan.
    expected_plan = make_current_plan(firmware, plan["dim7"])
    if plan != expected_plan:
        raise ValueError("current plan does not match its exact firmware-derived form")
    guard = next((g for g in plan["guards"] if int(g["address"], 16) == base), None)
    if guard is None:
        raise ValueError("table not covered by current plan")
    before, after = bytes.fromhex(guard["before_hex"]), bytes.fromhex(guard["after_hex"])
    expected, result = (after, before) if restore else (before, after)
    if bytes(current) != expected:
        raise ValueError("PMIC init table ownership/before-image mismatch")
    return result


class NativeAssertion(RuntimeError):
    pass


class PmicModel:
    STACK, STOP, STUBS, FIXTURE = 0x10000000, 0x10100000, 0x10200000, 0x11000000
    PMIC, ADAPTER, ADAPTER_VTABLE, LCD = (0x11000000, 0x11000100,
                                       0x11000200, 0x11000300)
    WRITE, READ = 0x10200000, 0x10200004
    SELECTOR, ASSERT = 0xC00B8760, 0xC0011100

    def __init__(self, firmware, *, selector=0, plan=None):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import arm_const
        self.reg = arm_const
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(0xC0000000, 0x4000000)
        for base, data in firmware.segments:
            self.uc.mem_write(base, data)
        for base, size in ((self.STACK, 0x10000), (self.STOP, 0x1000),
                           (self.STUBS, 0x1000), (self.FIXTURE, 0x1000)):
            self.uc.mem_map(base, size)
        self.put32(self.PMIC, 0xC072C604)
        self.put32(self.PMIC + 4, self.ADAPTER)
        self.put32(self.ADAPTER + 0x18, self.ADAPTER_VTABLE)
        self.put32(self.ADAPTER_VTABLE + 0xC, self.WRITE)
        self.put32(self.ADAPTER_VTABLE + 0x10, self.READ)
        self.put32(self.LCD + 4, self.PMIC)
        if plan is not None:
            for base in INIT_TABLES:
                original = self.uc.mem_read(base, INIT_SIZE)
                self.uc.mem_write(base, guarded_init_table(original, firmware, plan, base))
        self.selector = selector
        self.registers = {4: 0xB2, 0xE: 0xA9}
        self.events = []
        self.write_error = 0
        self.read_error = 0
        self.allowed = RANGES
        self.reached_stop = False
        self.initial_sp = self.STACK + 0xFFF0
        self.uc.hook_add(UC_HOOK_CODE, self._code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._write)

    def put32(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def u32(self, address):
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def _return(self, value):
        lr = self.uc.reg_read(self.reg.UC_ARM_REG_LR)
        for n in (0, 1, 2, 3, 12):
            self.uc.reg_write(getattr(self.reg, f"UC_ARM_REG_R{n}"), 0xBAD00000 + n)
        self.uc.reg_write(self.reg.UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(self.reg.UC_ARM_REG_PC, lr)

    def _write(self, uc, access, address, size, value, data):
        if not self.STACK <= address < address + size <= self.STACK + 0x10000:
            raise AssertionError(f"unexpected native PMIC memory write {address:#x}+{size}")

    def _code(self, uc, address, size, data):
        if address == self.STOP:
            self.reached_stop = True
            uc.emu_stop()
            return
        if address == self.ASSERT:
            raise NativeAssertion(f"native PMIC assert line {uc.reg_read(self.reg.UC_ARM_REG_R1):#x}")
        if address == self.SELECTOR:
            self._return(self.selector)
            return
        if address in (self.WRITE, self.READ):
            r0, reg, count, buffer = [uc.reg_read(getattr(self.reg, f"UC_ARM_REG_R{n}"))
                                      for n in range(4)]
            sp = uc.reg_read(self.reg.UC_ARM_REG_SP)
            if r0 != self.ADAPTER or count != 1 or [self.u32(sp), self.u32(sp + 4)] != [1, 0]:
                raise AssertionError("unexpected native I2C adapter arguments")
            if address == self.WRITE:
                value = uc.mem_read(buffer, 1)[0]
                self.events.append({"op": "write", "register": reg, "value": value,
                                    "result": self.write_error})
                if not self.write_error:
                    self.registers[reg] = value
                self._return(self.write_error)
            else:
                value = self.registers.get(reg, 0)
                self.events.append({"op": "read", "register": reg, "value": value,
                                    "result": self.read_error})
                if not self.read_error:
                    if not self.STACK <= buffer < self.STACK + 0x10000:
                        raise AssertionError("native read destination is not local stack")
                    uc.mem_write(buffer, bytes([value]))
                self._return(self.read_error)
            return
        if not any(lo <= address and address + size <= hi for lo, hi in self.allowed):
            raise AssertionError(f"unapproved PMIC execution {address:#x}")

    def run(self, kind, value=0):
        entries = {"init": INIT, "set_dim": SET_DIM, "enable": ENABLE,
                   "power_test_init": POWER_TEST_INIT, "lcd_enable": LCD_ENABLE_CALLBACK}
        if kind not in entries:
            raise ValueError("unknown native PMIC entry")
        self.events.clear()
        self.reached_stop = False
        saved = {}
        for n in range(4, 12):
            register = getattr(self.reg, f"UC_ARM_REG_R{n}")
            saved[register] = 0x55550000 + n
            self.uc.reg_write(register, saved[register])
        self.uc.reg_write(self.reg.UC_ARM_REG_SP, self.initial_sp)
        self.uc.reg_write(self.reg.UC_ARM_REG_LR, self.STOP)
        self.uc.reg_write(self.reg.UC_ARM_REG_R0, self.LCD if kind == "lcd_enable" else self.PMIC)
        self.uc.reg_write(self.reg.UC_ARM_REG_R1, value & 0xFFFFFFFF)
        self.uc.emu_start(entries[kind], self.STOP + 4, count=5000)
        if not self.reached_stop:
            raise AssertionError("PMIC entry exceeded instruction budget")
        if self.uc.reg_read(self.reg.UC_ARM_REG_SP) != self.initial_sp:
            raise AssertionError("native PMIC entry did not restore SP")
        if any(self.uc.reg_read(r) != v for r, v in saved.items()):
            raise AssertionError("native PMIC entry damaged callee-saved registers")
        return list(self.events)
