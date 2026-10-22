#!/usr/bin/env python3
"""Execute a delivered Sensor Lab card's core and late hook paths offline.

The B2_5 page parser itself is covered by the host sl_menu tests.  This test
replaces only that parser call with success so the actual ARM launcher, USER
relocations, journal gate, UI hook installer and power-off callback all run.
It never opens a camera or writes a card.  Pass the fresh card directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2] / "fpSup/fp_usb_shell")]
import build_res_lab_card as CARD
import imx410_plan as PL
from res_lab_user_pack import res_lab_pack
import test_loader_hook as LOADER
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2


class MigratedCamera(LOADER.Camera):
    def __init__(self, card: Path, *, early_gate_refused=False, late_gate_refused=False):
        self.manifest = json.loads((card / "MANIFEST.json").read_text())
        autorun = (card / "AutoRun.txt").read_text()
        loader = {int(address, 16): int(value, 16) for address, value in
                  re.findall(r"^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)", autorun, re.M)
                  if LOADER.CAVE_LOW <= int(address, 16) < LOADER.CAVE_LOW + 0x200}
        super().__init__(loader, (card / "fpSup.BIN").read_bytes())
        self.user_allocs = (LOADER.HEAP, LOADER.HEAP + 0x100000,
                            LOADER.HEAP + 0x110000)
        self.alloc_count = 0
        self.menu_installs = 0
        self.page_publications = []
        self.gate_calls = 0
        self.early_gate_refused = early_gate_refused
        self.late_gate_refused = late_gate_refused
        self.gate_pc = self.user_allocs[1] + self.manifest["core"]["journal_gate_off"]
        self.worker_pc = None  # the loader chooses a file buffer offset at F_READ
        menu = self.manifest["b25_menu"]
        self.install_pc = (self.user_allocs[2] + menu["installer"]["c_base"] +
                           (menu["installer"]["install"] & ~1)) if menu else None
        if menu:
            self.page_entry = 0xC3001000
            self.private_page = self.user_allocs[2] + menu["installer"]["area_off"] + 0x1000
            self.mu.mem_write(self.page_entry + 8, struct.pack("<I", 0x19C130))
            self.mu.hook_add(UC_HOOK_MEM_WRITE, self._page_write,
                             begin=self.page_entry + 8, end=self.page_entry + 11)

    def _page_write(self, _mu, _access, _address, _size, value, _data):
        armed = all(self.word(int(site, 16)) !=
                    int(self.manifest["core"]["dynamic_stock_sites"][site], 16)
                    for site in self.manifest["core"]["late_ui_hook_sites"])
        self.page_publications.append((value, armed))

    def _hook(self, mu, address, size, data):
        if address == self.worker_pc:
            self.calls.append("WORKER_STUB")
            return self._ret(0)
        if address == LOADER.F["H_GET"]:
            self.alloc_count += 1
            assert self.alloc_count <= len(self.user_allocs)
            self.calls.append("H_GET")
            return self._ret(0)
        if address == LOADER.F["H_ADDR"]:
            self.calls.append("H_ADDR")
            return self._ret(self.user_allocs[self.alloc_count - 1])
        if address == LOADER.F["POFF_ADD"]:
            obj, forced = self.r(UC_ARM_REG_R1), self.r(UC_ARM_REG_R2)
            mu.mem_write(0xC3000100 + (0x34 if forced else 0x0C), struct.pack("<I", obj))
        if address == LOADER.F["F_READ"]:
            target, capacity = self.r(UC_ARM_REG_R1), self.r(UC_ARM_REG_R2)
            if self.manifest["debug"]:
                self.worker_pc = target + int(self.manifest["entry_check"]["entries"][0], 16)
            mu.mem_write(target, self.bin[:capacity])
            self.calls.append("F_READ")
            return self._ret(min(len(self.bin), capacity))
        if address == self.gate_pc:
            self.gate_calls += 1
            if self.early_gate_refused and self.gate_calls == 1:
                self.calls.append("CORE_GATE_REFUSED")
                return self._ret(0)
            if self.late_gate_refused and self.gate_calls == 2:
                self.calls.append("UI_GATE_REFUSED")
                return self._ret(0)
        if address == self.install_pc:
            self.menu_installs += 1
            self.calls.append("UI_INSTALL_STUB")
            state = self.user_allocs[2] + self.manifest["b25_menu"]["installer"]["state_off"]
            mu.mem_write(state + 12, struct.pack("<II", self.page_entry, self.private_page))
            return self._ret(1)
        if address == 0xC0057AE8:  # original resolution object getter
            return self._ret(0xC3000300)
        if address == 0xC005BE90:  # original recording format getter
            return self._ret(0)
        return super()._hook(mu, address, size, data)

    def boot(self):
        result = self.call(LOADER.CAVE_LOW)
        assert result[1] == LOADER.STACK - 0x1004, "entry stack was not restored"
        assert ("WORKER_STUB" in self.calls) == self.manifest["debug"]
        want_allocations = 2 if self.early_gate_refused else (3 if self.manifest["b25_menu"] else 2)
        assert self.alloc_count == want_allocations, "late UI discovery/allocation failed"
        assert len(self.registered) == 2 and self.registered[0][0] == self.registered[1][0]
        assert [flag for _, flag in self.registered] == [0, 1]
        return result


def verify(card: Path):
    manifest = json.loads((card / "MANIFEST.json").read_text())
    assert manifest["core"]["core_bytes"] < 0x10000
    camera = MigratedCamera(card)
    camera.boot()
    core_base = camera.user_allocs[1]
    is_menu = bool(manifest["b25_menu"])
    if is_menu:
        assert camera.menu_installs == 1, "private B2_5 install did not run"
        assert camera.page_publications == [((camera.private_page - 0xC18C0460) & 0xFFFFFFFF, True)], \
            "private B2_5 page was not published after every late hook"
        refused = MigratedCamera(card, late_gate_refused=True)
        refused.boot()
        assert refused.gate_calls == 2 and refused.menu_installs == 1
        assert all(refused.word(int(site, 16)) ==
                   int(manifest["core"]["dynamic_stock_sites"][site], 16)
                   for site in manifest["core"]["late_ui_hook_sites"]), \
            "late gate refusal armed a UI hook"
        assert refused.word(refused.page_entry + 8) == 0x19C130, \
            "late gate refusal exposed the private page"
        mark = refused.user_allocs[1] + manifest["core"]["core_offsets"]["mark"]
        assert refused.word(mark + 12) == 12, "late gate refusal lacks its result code"
    early = MigratedCamera(card, early_gate_refused=True)
    early.boot()
    assert early.gate_calls == 1 and early.menu_installs == 0
    assert all(early.word(int(site, 16)) == int(stock, 16)
               for site, stock in manifest["core"]["dynamic_stock_sites"].items()), \
        "core gate refusal changed a dynamic firmware site"

    # Runtime relocation must produce the same USER bytes as the independent
    # offline transform.  The gate appended after the magic is checked by the
    # artifact audit and is executed here before either set of hooks arms.
    saved = (PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW)
    try:
        PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = is_menu, False, False
        with CARD.source_directory():
            pack = res_lab_pack(CARD.card_items(), firmware=PL.FIRMWARE.read_bytes())
    finally:
        PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = saved
    actual = bytes(camera.mu.mem_read(core_base, len(pack.image)))
    expected = pack.materialize(core_base)
    mutable = set()
    for old_address in PL.volatile_addresses():
        try:
            offset = pack.address_map(old_address)
        except ValueError:
            continue
        mutable.update(range(offset, offset + 4))
    changed = {index for index, (got, want) in enumerate(zip(actual, expected)) if got != want}
    assert changed <= mutable, "runtime USER code/table differs outside declared state"
    for relocation in pack.relocations:
        off = relocation.source_offset
        size = 8 if relocation.kind == 2 else 4
        assert actual[off:off + size] == expected[off:off + size], \
            f"runtime relocation differs at USER+{off:#x}"
    for address in manifest["core"]["hook_sites"]:
        address = int(address, 16)
        assert camera.word(address) != int(manifest["core"]["dynamic_stock_sites"][f"0x{address:08X}"], 16), \
            f"deferred hook was not armed at {address:#x}"
    for address in manifest["core"]["pointer_sites"]:
        address = int(address, 16)
        assert camera.word(address) != int(manifest["core"]["dynamic_stock_sites"][f"0x{address:08X}"], 16), \
            f"external pointer was not relocated at {address:#x}"
    cave_lo, cave_hi = 0xC0730000, 0xC0735000
    assert bytes(camera.mu.mem_read(cave_lo, cave_hi - cave_lo)) == \
        camera.stock[cave_lo - PL.B:cave_hi - PL.B], "factory cave data changed"

    # Both registered power-off paths are safe to call; replay every non-cave
    # VBIN section, including the later runtime-modified stock-word sections.
    obj = camera.registered[0][0]
    callback = camera.word(obj + 4)
    for _ in range(2):
        camera.call(callback, r0=obj, r1=4)
    _entry, records = CARD.decode(camera.bin[:0xF000] if is_menu else camera.bin)
    restored = 0
    for address, _, data in records:
        if address < 0x40000000 or 0xC072D000 <= address < 0xC0735000:
            continue
        expected = camera.stock[address - PL.B:address - PL.B + len(data)]
        assert bytes(camera.mu.mem_read(address, len(data))) == expected, \
            f"power-off did not restore {address:#x}"
        restored += 1
    assert restored == manifest["core"]["journal_max"]
    return {"card": str(card), "core_hooks": len(manifest["core"]["core_hook_sites"]),
            "ui_hooks": len(manifest["core"]["late_ui_hook_sites"]),
            "journal_records_restored": restored,
            "late_gate_refusal_leaves_stock_ui": is_menu,
            "early_gate_refusal_leaves_all_sites_stock": True,
            "factory_cave_bytes_preserved": cave_hi - cave_lo}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", type=Path)
    print(json.dumps(verify(parser.parse_args().card), indent=2))
