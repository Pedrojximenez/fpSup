#!/usr/bin/env python3
"""OG3K — 從乾淨冷開機的 USB shell 安全載入測試 resident。

這不是熱升級器。只接受兩種完整狀態：全原廠，或同一份 plan 已完整安裝。
任何舊版、部分安裝、未知 hook、非零 cave 或掉寫都停止並要求拔電池冷開；
不會在不完整 payload 上掛 hook。

    ./og3k_load.py            從全原廠狀態安裝
    ./og3k_load.py --check    只做快照與分類，零寫入
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from putfile import (ECHO_ORIG, ECHO_SLOT, mem_get, mem_set, sh)  # noqa: E402
from og3k_plan import (BUFFER_COUNT_ADDR, EMIT_FN, EMIT_H, EMIT_W, HOOKS,
                       DONOR_NOMINAL_FPS_ADDR, DONOR_TIMING_ADDR, OWNED,
                       STRHI, STRLO, Plan)  # noqa: E402

CHECK = "--check" in sys.argv
F_DCACHE = 0xC000E91C            # D-cache clean+invalidate, DSB, ISB
F_ICACHE = 0xC000EABC            # entire I-cache invalidate, DSB, ISB
PRIVATE_LO, PRIVATE_HI = 0xC0730000, 0xC0740000
LEGACY_FPS_STATE = 0xC0730704


class ReadFailed(RuntimeError):
    pass


class WriteFailed(RuntimeError):
    pass


class CacheFailed(RuntimeError):
    pass


def rd(address: int, tries: int = 10) -> int:
    for _ in range(tries):
        words = mem_get(address)
        if words and words[0] is not None:
            return words[0]
    raise ReadFailed(f"read 0x{address:08X}")


def write_verified(address: int, value: int, tries: int = 12) -> bool:
    """Write one word and prove it; return whether a change was needed."""
    if rd(address) == value:
        return False
    for _ in range(tries):
        mem_set(address, value)
        if rd(address) == value:
            return True
    raise WriteFailed(f"write 0x{address:08X}=0x{value:08X}")


def call_firmware_noargs(function: int) -> None:
    """Temporarily borrow echo's handler to call an idempotent no-arg routine."""
    if rd(ECHO_SLOT) != ECHO_ORIG:
        raise CacheFailed(f"echo handler 0x{ECHO_SLOT:08X} is not stock")
    primary: Exception | None = None
    try:
        write_verified(ECHO_SLOT, function)
        reply = sh("echo", retries=3)
        if reply.startswith("ERR"):
            raise CacheFailed(f"call 0x{function:08X}: {reply.strip()}")
    except Exception as error:  # restoration below is mandatory
        primary = error
    try:
        write_verified(ECHO_SLOT, ECHO_ORIG, tries=20)
    except Exception as restore_error:
        if primary is not None:
            raise CacheFailed(f"{primary}; echo restore also failed: {restore_error}")
        raise CacheFailed(f"echo restore failed: {restore_error}")
    if primary is not None:
        raise primary


def sync_code() -> None:
    """Publish live code writes: data first, then invalidate instruction cache."""
    call_firmware_noargs(F_DCACHE)
    call_firmware_noargs(F_ICACHE)


@dataclass
class CameraIO:
    def read(self, address: int) -> int:
        return rd(address)

    def write(self, address: int, value: int) -> bool:
        return write_verified(address, value)

    def sync(self) -> None:
        sync_code()


def read_snapshot(io, addresses: set[int]) -> dict[int, int]:
    """Read every address before the first write; fail as one read-only phase."""
    snapshot = {}
    failures = []
    for address in sorted(addresses):
        try:
            snapshot[address] = io.read(address)
        except Exception as error:
            failures.append(f"0x{address:08X}: {error}")
            if len(failures) == 7:
                break
    if failures:
        raise ReadFailed("; ".join(failures))
    return snapshot


def _immutable_addresses(plan: Plan) -> set[int]:
    """Words that cannot legitimately drift after a complete installation."""
    volatile = {address for address, _, _ in plan.state()}
    for addresses, _, _ in plan.groups():
        volatile.update(addresses)
    return {address for address, _, _ in plan.all()} - volatile


def _rollback(io, exec_sites: set[int], stock: dict[int, int],
              external_changed: list[int]) -> list[str]:
    errors = []
    for address in sorted(exec_sites):
        try:
            io.write(address, stock[address])
        except Exception as error:
            errors.append(str(error))
    for address in reversed(external_changed):
        try:
            io.write(address, stock[address])
        except Exception as error:
            errors.append(str(error))
    try:
        io.sync()
    except Exception as error:
        errors.append(f"cache rollback: {error}")
    for address in sorted(exec_sites):
        try:
            if io.read(address) != stock[address]:
                errors.append(f"0x{address:08X} is not stock after rollback")
        except Exception as error:
            errors.append(str(error))
    return errors


def apply(plan: Plan | None = None, io=None, check: bool = False) -> int:
    plan = plan or Plan()
    io = io or CameraIO()
    static_errors = plan.check()
    if static_errors:
        for error in static_errors:
            print("  " + error)
        print("★ 靜態檢查失敗；零寫入")
        return 1

    items = list(plan.all())
    desired = {address: value for address, value, _ in items}
    if len(desired) != len(items):
        print("★ plan 有重複位址；零寫入")
        return 1

    active_sites = {site for site, _, _, _, _ in HOOKS}
    exec_sites = set(OWNED) | active_sites | {EMIT_FN}
    if not active_sites <= exec_sites:
        print("★ hook ownership 表不完整；零寫入")
        return 1
    stock = {address: plan.word(address) for address in set(desired) | exec_sites}
    plan_hooks = {site: desired[site] for site in active_sites}
    inactive_sites = exec_sites - active_sites

    group_writes = []
    for addresses, _, off in plan.groups():
        group_writes.extend((address, off, "未選中群組值") for address in addresses)
        stock.update((address, plan.word(address)) for address in addresses)

    # 舊版曾碰過但本版不再寫的共享欄位，也必須證明是冷開基準；否則即使
    # hooks 恰好已拆，仍可能把殘留狀態誤認成乾淨相機。
    safety_baseline = {DONOR_TIMING_ADDR + 4, DONOR_TIMING_ADDR + 8,
                       DONOR_NOMINAL_FPS_ADDR, BUFFER_COUNT_ADDR,
                       EMIT_W, EMIT_H, STRLO, STRHI, LEGACY_FPS_STATE}
    stock.update((address, plan.word(address)) for address in safety_baseline)

    snapshot_addresses = (set(desired) | exec_sites |
                          {address for address, _, _ in group_writes} |
                          safety_baseline | {ECHO_SLOT, F_DCACHE, F_ICACHE})
    print("OG3K " + ("安全檢查" if check else "冷開安裝") + "\n")
    try:
        snapshot = read_snapshot(io, snapshot_addresses)
    except ReadFailed as error:
        print(f"★ 預檢讀取失敗；零寫入：{error}")
        return 1
    print(f"  預檢 {len(snapshot_addresses)} 個位址全部可讀")

    if snapshot[ECHO_SLOT] != ECHO_ORIG:
        print("★ echo handler 已被占用；零寫入，請拔電池冷開")
        return 1
    for function in (F_DCACHE, F_ICACHE):
        if snapshot[function] != plan.word(function):
            print(f"★ cache routine 0x{function:08X} signature 不符；零寫入")
            return 1

    foreign = []
    for address in sorted(exec_sites):
        allowed = {stock[address]}
        if address in plan_hooks:
            allowed.add(plan_hooks[address])
        if snapshot[address] not in allowed:
            foreign.append((address, snapshot[address]))
    if foreign:
        for address, value in foreign[:6]:
            print(f"  0x{address:08X}=0x{value:08X} 不是原廠或本版 hook")
        print("★ 發現未知/舊版執行入口；零寫入，請拔電池冷開")
        return 1

    hook_state = {snapshot[site] == plan_hooks[site] for site in active_sites}
    if hook_state == {True}:
        immutable = _immutable_addresses(plan)
        drift = [(address, snapshot[address], desired[address])
                 for address in sorted(immutable)
                 if snapshot[address] != desired[address]]
        inactive_drift = [address for address in inactive_sites
                          if snapshot[address] != stock[address]]
        if drift or inactive_drift:
            print("★ resident hook 已存在但內容不是本版完整 plan；零寫入，請冷開")
            return 1
        print("★ 同一份 resident 已完整安裝；零寫入")
        return 0
    if hook_state != {False}:
        print("★ hooks 是部分安裝狀態；零寫入，請拔電池冷開")
        return 1

    dirty_stock = [(address, snapshot[address], stock[address])
                   for address in sorted(set(desired) | safety_baseline |
                                         {a for a, _, _ in group_writes})
                   if snapshot[address] != stock[address]]
    if dirty_stock:
        for address, value, expected in dirty_stock[:6]:
            print(f"  0x{address:08X}=0x{value:08X}，冷開基準應為 0x{expected:08X}")
        print("★ 不是乾淨冷開狀態；零寫入，請拔電池後再試")
        return 1

    changes = sum(snapshot[address] != desired[address] for address in desired)
    if check:
        print(f"★ 可安全做第一次安裝；預計改 {changes} 字；本次零寫入")
        return 0

    body = [(address, value, note) for address, value, note in items
            if address not in exec_sites]
    # 先放 private cave，最後才碰會立刻影響選單/表格的 firmware data。
    body.sort(key=lambda item: 0 if PRIVATE_LO <= item[0] < PRIVATE_HI else 1)
    external_changed: list[int] = []
    changed = 0
    try:
        for address, value, _ in body + group_writes:
            did_change = io.write(address, value)
            changed += int(did_change)
            if did_change and not (PRIVATE_LO <= address < PRIVATE_HI):
                external_changed.append(address)
    except Exception as error:
        rollback_errors = _rollback(io, exec_sites, stock, external_changed)
        print(f"★ body 寫入失敗：{error}；沒有掛上本版 hook")
        if rollback_errors:
            print("  回復也不完整，必須拔電池：" + "; ".join(rollback_errors[:4]))
        return 1

    try:
        io.sync()
    except Exception as error:
        rollback_errors = _rollback(io, exec_sites, stock, external_changed)
        print(f"★ payload cache 同步失敗：{error}；沒有掛上本版 hook")
        if rollback_errors:
            print("  回復也不完整，必須拔電池：" + "; ".join(rollback_errors[:4]))
        return 1

    armed = []
    try:
        # HOOKS 的宣告順序是依賴端先、picker 最後；不要排序。
        for site, _, _, _, _ in HOOKS:
            changed += int(io.write(site, plan_hooks[site]))
            armed.append(site)
        io.sync()
        for site in active_sites:
            if io.read(site) != plan_hooks[site]:
                raise WriteFailed(f"hook verify 0x{site:08X}")
    except Exception as error:
        rollback_errors = _rollback(io, exec_sites, stock, external_changed)
        print(f"★ hook commit 失敗：{error}；已要求全部回原廠")
        if rollback_errors:
            print("  無法證明已回復，必須拔電池：" + "; ".join(rollback_errors[:4]))
        return 1

    print(f"  計畫 {len(items)} 筆；改了 {changed} 字；payload 與 hooks 都已讀回")
    print("★ 全部就緒（只允許本次冷開 session；更新版本前仍須拔電池）")
    return 0


def main() -> int:
    return apply(check=CHECK)


if __name__ == "__main__":
    raise SystemExit(main())
