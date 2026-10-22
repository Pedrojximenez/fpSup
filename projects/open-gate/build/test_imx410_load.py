#!/usr/bin/env python3
"""imx410_load 的狀態機,離線跑完,零相機。

載入器是整套裡最危險的一段:寫壞了相機就凍。所以四種相機狀態各測一次,
而且**每一條失敗路徑都要證明它真的回復了** —— 注入寫入失敗,檢查有沒有留下
半套狀態。

    python3 test_imx410_load.py
"""
from __future__ import annotations

import pathlib
import sys
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import imx410_load as LD
import imx410_plan as PL

IMG = PL.FIRMWARE.read_bytes()
B = 0xC0000000
ITEMS = PL.plan()
DESIRED = {a: v for a, v, _ in ITEMS}
HOOKS = [a for a, _, n in ITEMS if "hook" in n]


def stock(addr):
    return int.from_bytes(IMG[addr - B: addr - B + 4], "little")


def og3k_state():
    """相機上跑著完整 OG3K 時的樣子 —— 2026-09-28 實際讀到的狀態。"""
    return LD._other_plan("og3k")


def offline_apply(io, *, image=IMG, **kw):
    """Exercise the archived state machine with FakeIO only.

    The public entry point is intentionally blocked by the cave safety gate.
    These older transition tests retain their value, but must never connect to
    a camera or be mistaken for proof that this plan is safe to install.
    """
    assert isinstance(io, LD.FakeIO), "offline state-machine tests require FakeIO"
    with patch.object(LD, "_preflight_safe_plan", return_value=None):
        return LD.apply(io, image=image, **kw)


def run(overrides=None, **kw):
    io = LD.FakeIO(IMG, overrides)
    rc = offline_apply(io, image=IMG, **kw)
    return rc, io


def test_public_apply_blocks_every_mode_before_any_io():
    class ForbiddenIO:
        def read(self, *_args, **_kw):
            raise AssertionError("unsafe plan reached camera read")

        def write(self, *_args, **_kw):
            raise AssertionError("unsafe plan reached camera write")

        def sync(self):
            raise AssertionError("unsafe plan reached camera cache sync")

    for kw in ({}, {"check": True}, {"stage": 0}, {"stage": 2},
               {"disarm": True}, {"check": True, "disarm": True}):
        with redirect_stdout(StringIO()) as output:
            assert LD.apply(ForbiddenIO(), image=IMG, **kw) == 1, kw
        assert "零相機 I/O" in output.getvalue(), (kw, output.getvalue())


def test_main_blocks_every_mode_before_cameraio_construction():
    argv_cases = ([], ["--check"], ["--stage", "0"],
                  ["--stage", "2"], ["--disarm"],
                  ["--check", "--disarm"], ["--axis-preset", "A"])
    with patch.object(LD, "CameraIO", side_effect=AssertionError("camera opened")) as ctor:
        for argv in argv_cases:
            with redirect_stdout(StringIO()) as output:
                assert LD.main(argv) == 1, argv
            assert "零相機 I/O" in output.getvalue(), (argv, output.getvalue())
        assert ctor.call_count == 0, ctor.call_count


# ---- 四種狀態 --------------------------------------------------------------
def test_stock_installs():
    rc, io = run()
    assert rc == 0, rc
    for a, v in DESIRED.items():
        assert io.read(a) == v, (hex(a), hex(io.read(a)), hex(v))


def test_hooks_are_armed_last():
    """payload 一定要在指著它的 hook 之前寫完。"""
    _, io = run()
    order = [a for a, _ in io.writes]
    first_hook = min(order.index(h) for h in HOOKS if h in order)
    body = [a for a, _ in io.writes if a not in set(HOOKS)]
    assert all(order.index(a) < first_hook for a in body), "有 body 排在 hook 之後"


def test_already_installed_is_a_noop():
    rc, io = run(overrides=dict(DESIRED))
    assert rc == 0
    assert io.writes == [], io.writes[:5]


def test_installed_but_drifted_refuses():
    ov = dict(DESIRED)
    victim = next(a for a in DESIRED if LD.PRIVATE_LO <= a < LD.PRIVATE_HI
                  and a not in set(HOOKS))
    ov[victim] = 0xDEADBEEF
    rc, io = run(overrides=ov)
    assert rc == 1
    assert io.writes == [], "掉寫狀態下不可以寫任何東西"


def test_our_own_partial_is_allowed():
    """一半是**我們自己**的值 = 分段安裝停在中間,可以繼續。"""
    ov = {HOOKS[0]: DESIRED[HOOKS[0]]}
    rc, io = run(overrides=ov)
    assert rc == 0, rc
    for a, v in DESIRED.items():
        assert io.read(a) == v, hex(a)


def test_partial_with_a_foreign_value_refuses():
    """混進一個**不是我們也不是原廠**的值 -> 證不出來,零寫入。"""
    ov = {HOOKS[0]: DESIRED[HOOKS[0]], HOOKS[1]: 0xEA000123}
    rc, io = run(overrides=ov)
    assert rc == 1, rc
    assert io.writes == [], io.writes[:5]


def test_foreign_refuses_without_disarm():
    """相機上跑著 OG3K 時,不帶 --disarm 一定要零寫入。"""
    rc, io = run(overrides=og3k_state())
    assert rc == 1
    assert io.writes == [], io.writes[:5]


# ---- 解除 ------------------------------------------------------------------
def test_disarm_then_install():
    rc, io = run(overrides=og3k_state(), disarm=True)
    assert rc == 0, rc
    for a, v in DESIRED.items():
        assert io.read(a) == v, (hex(a), hex(io.read(a)), hex(v))


def test_disarm_restores_foreign_firmware_data():
    """OG3K 動過的**原廠資料**(選單 CSV、控制器上限、donor 時序…)要回原廠。

    只拆 hook 不夠 —— 那些位址留著就是髒狀態,而且我們不一定會蓋過去。
    """
    og = og3k_state()
    foreign = LD.foreign_addresses()
    dirty = [a for a in foreign if og.get(a, stock(a)) != stock(a)]
    assert dirty, "OG3K 應該有動過原廠資料,推導壞了"
    _, io = run(overrides=og, disarm=True)
    for a in dirty:
        # 要嘛回原廠,要嘛被我們自己的計畫蓋成新值 —— 不可以留著 OG3K 的
        assert io.read(a) in (stock(a), DESIRED.get(a)), \
            f"0x{a:08X} 還是 OG3K 的值 {io.read(a):#x}"


def test_disarm_unhooks_before_touching_payloads():
    """★ 這是整個載入器最重要的一條。

    2026-09-12:逐字覆寫一段被 hook 指著、每秒執行幾十次的 payload,相機當場
    當掉。所以**所有** hook 必須在第一個 payload 字之前就回到原廠。
    """
    og = og3k_state()
    _, io = run(overrides=og, disarm=True)
    order = [a for a, _ in io.writes]
    armed = [h for h in HOOKS if og.get(h, stock(h)) != stock(h)]
    assert armed, "OG3K 應該有武裝的 hook"
    last_unhook = max(order.index(h) for h in armed)
    payloads = [i for i, a in enumerate(order)
                if LD.PRIVATE_LO <= a < LD.PRIVATE_HI]
    assert payloads, "沒有寫任何 payload?"
    assert min(payloads) > last_unhook, \
        "有 payload 字寫在 hook 還武裝著的時候 —— 這就是會凍結的那個動作"


def test_foreign_set_is_derived_not_hardcoded():
    """解除的位址集合是從別的產品自己的計畫推導的。"""
    f = LD.foreign_addresses()
    assert len(f) > 20, len(f)
    assert all(not (LD.PRIVATE_LO <= a < LD.PRIVATE_HI) for a in f)
    # 選單 CSV 與控制器上限一定在裡面
    assert PL.CTRL_CAP in f
    assert any(PL.CSV_ADDR <= a < PL.CSV_ADDR + 92 for a in f)


# ---- 失敗路徑 --------------------------------------------------------------
def _write_count(**kw):
    """一次乾淨安裝實際會寫幾個字 —— 很多筆本來就等於原值,不會寫。"""
    io = LD.FakeIO(IMG)
    offline_apply(io, image=IMG, **kw)
    return len(io.writes)


def test_body_failure_rolls_back_external_writes():
    """body 寫到一半失敗:原廠資料要回去,而且一個 hook 都不能掛。"""
    total = _write_count()
    io = LD.FakeIO(IMG)
    io.fail_at = total - len(HOOKS) - 3      # body 快寫完時炸掉
    rc = offline_apply(io, image=IMG)
    assert rc == 1, f"注入失敗卻回 {rc}(總寫入 {total})"
    for h in HOOKS:
        assert io.read(h) == stock(h), f"0x{h:08X} 被掛上了"
    for a in io.mem:
        if not (LD.PRIVATE_LO <= a < LD.PRIVATE_HI):
            assert io.read(a) == stock(a), f"原廠資料 0x{a:08X} 沒回復"


def test_hook_failure_rolls_back_hooks():
    """武裝到一半失敗:已經掛上的要全部拆回原廠。"""
    total = _write_count()
    io = LD.FakeIO(IMG)
    io.fail_at = total - 2               # 掛了幾個 hook 之後炸掉
    rc = offline_apply(io, image=IMG)
    assert rc == 1
    for h in HOOKS:
        assert io.read(h) == stock(h), f"0x{h:08X} 留在武裝狀態"


def test_check_never_writes():
    for ov in (None, og3k_state(), dict(DESIRED)):
        _, io = run(overrides=ov, check=True)
        assert io.writes == [], io.writes[:5]


def test_camera_io_unwraps_mem_get():
    """★ `mem_get` 回傳 list,沒回來的字是 None。

    2026-09-28 我把它當 int 用,於是每一次比較都是 `list != int` 恆真 ——
    分類器永遠說 foreign。離線的 FakeIO 回傳 int,所以 13 個測試全過也抓不到。
    這一個用 stub 直接釘住 CameraIO 的契約。
    """
    calls = []

    def fake_get(addr, count=1):
        calls.append((addr, count))
        return [0x11223344 + i for i in range(count)]

    io = LD.CameraIO(mem_get=fake_get, mem_set=lambda a, v: None, sh=lambda c: "")
    v = io.read(0xC0730000)
    assert isinstance(v, int), type(v)
    assert v == 0x11223344, hex(v)
    assert io.read_many(0xC0730000, 3) == [0x11223344, 0x11223345, 0x11223346]

    def missing(addr, count=1):
        return [None] * count

    io2 = LD.CameraIO(mem_get=missing, mem_set=lambda a, v: None, sh=lambda c: "")
    for fn in (lambda: io2.read(0xC0730000), lambda: io2.read_many(0xC0730000, 2)):
        try:
            fn()
        except LD.ReadFailed:
            pass
        else:
            raise AssertionError("掉字的讀取要抛 ReadFailed,不能回 None")


def test_snapshot_batches_runs():
    """連續位址要併成一次讀 —— 1400 個位址逐字來回太慢,也多 1400 次掉字機會。"""
    calls = []

    def fake_get(addr, count=1):
        calls.append((addr, count))
        return [0] * count

    io = LD.CameraIO(mem_get=fake_get, mem_set=lambda a, v: None, sh=lambda c: "")
    run = [0xC0730000 + i * 4 for i in range(40)]
    LD._snapshot(io, set(run) | {0xC0740000})
    assert max(c for _, c in calls) >= 40, calls
    assert len(calls) <= 3, calls


def test_sync_failure_aborts_before_arming():
    """★ cache 同步失敗,一個 hook 都不可以掛。

    2026-09-28 上機凍結的根因:我的 sync 送了 shell 根本沒有的 `call` 指令
    (回 `not found cmd "call"`),而且**沒有檢查回覆**。1295 個字的新程式碼
    從來沒發布到 I-cache,picker hook 一掛,CPU 就跳進舊的快取行執行。

    同步失敗必須跟寫入失敗一樣致命。
    """
    class BadSync(LD.FakeIO):
        def sync(self):
            raise LD.WriteFailed("cache 同步失敗")

    io = BadSync(IMG)
    rc = offline_apply(io, image=IMG)
    assert rc == 1, "同步失敗卻回成功"
    for h in HOOKS:
        assert io.read(h) == stock(h), f"0x{h:08X} 在沒同步的情況下被掛上"


def test_loader_does_not_invent_shell_commands():
    """載入器不可以自己發明 shell 指令。

    shell 沒有 `call`。呼叫韌體常式的唯一做法是 og3k_load 那個
    borrow-echo-handler 的機制 —— 它已經驗證過,而且會強制還原 echo slot。
    """
    src = pathlib.Path("imx410_load.py").read_text()
    assert '"call ' not in src and "'call " not in src and 'f"call' not in src, \
        "又自己發明 call 指令了"
    assert "sync_code" in src, "應該用 og3k_load 驗證過的 sync_code"


def test_sync_runs_after_body_and_before_hooks():
    """順序:body -> sync -> 武裝。沒有中間那一步,hook 指向的是舊快取行。"""
    events = []

    class Tracking(LD.FakeIO):
        def write(self, addr, value):
            r = super().write(addr, value)
            if r:
                events.append(("hook" if addr in set(HOOKS) else "body", addr))
            return r

        def sync(self):
            events.append(("sync", None))
            super().sync()

    io = Tracking(IMG)
    assert offline_apply(io, image=IMG) == 0
    kinds = [k for k, _ in events]
    first_hook = kinds.index("hook")
    assert "sync" in kinds[:first_hook], "武裝之前沒有同步過"
    assert kinds[-1] == "sync" or "sync" in kinds[first_hook:], "武裝之後也要同步"


def test_staged_install_is_idempotent():
    """分段武裝:一階段一階段裝上去,每一次都要接得上前一次。"""
    import imx410_plan as P
    io = LD.FakeIO(IMG)
    n = len(P._stages())
    for k in range(n + 1):
        rc = offline_apply(io, image=IMG, stage=k)
        assert rc == 0, f"階段 {k} 回 {rc}"
    full = {a: v for a, v, _ in P.plan()}
    for a, v in full.items():
        assert io.read(a) == v, (hex(a), hex(io.read(a)), hex(v))


def test_picker_is_armed_last():
    """★ picker 一掛,整組就活了。它必須是最後一個。

    og3k_plan 的 HOOKS 註解:「依賴端先、picker 最後」,og3k_load 還特地
    註明「不要排序」。第一版把 picker 放第一個 —— 等於在畫布、長寬比、增益
    都還沒就位時就讓它開始發放表項。
    """
    import imx410_plan as P
    items = P.plan()
    hooks = [a for a, _, n in items if "hook" in n]
    assert hooks[-1] == P.PIK_HOOK, [hex(h) for h in hooks]
    assert hooks[0] == P.ROW_HOOK, "畫布應該第一個(它有 profile 守衛)"
    assert P._stages()[-1][0] == "picker"


def test_runtime_slots_do_not_look_foreign():
    """★ payload 一跑就會改自己的紀錄槽 —— 那不是髒,是設計。

    2026-09-28 上機:畫布 hook 掛上之後把「最後看到的 profile = 5」寫進
    0xC0732A08,下一階段的分類就把整台相機判成 foreign,拒絕繼續。
    og3k_load 的 §8c 記過反方向的同一個坑(把真的壞掉當成 log 槽打發)。
    所以這張表要**明確列出**,不能用「cave 裡的都不算」帶過。
    """
    import imx410_plan as P
    vol = P.volatile_addresses()
    assert 0xC0732A08 in vol, "畫布的『最後 profile』槽沒列進去"
    assert P.RECIPE in vol and P.CANVAS in vol and P.HITS in vol
    assert all(P.AXIS + i * 4 in vol for i in range(9)), "選單改 AXIS 不應判為外來版本"
    # hook 本身**不可以**是 volatile —— 那是分類唯一的依據
    hooks = {a for a, _, n in P.plan() if "hook" in n}
    assert not (hooks & vol), [hex(a) for a in hooks & vol]

    # 裝好之後讓每一個 volatile 槽都偏離初值,仍然要認得是自己裝的
    ov = dict(DESIRED)
    for i, a in enumerate(sorted(vol)):
        ov[a] = 0xA5A50000 + i
    rc, io = run(overrides=ov, check=True)
    assert rc == 0, "執行期槽偏離就認不出自己了"


def test_short_batch_reply_recovers_every_missing_word():
    def get(addr, count=1):
        return [123] if count > 1 else [addr]
    io = LD.CameraIO(mem_get=get, mem_set=lambda a, v: None)
    assert io.read_many(0x1000, 3) == [123, 0x1004, 0x1008]


def test_write_readback_mismatch_retries_boundedly():
    memory, writes = {}, []
    def put(addr, value):
        writes.append((addr, value))
        if len(writes) == 2:
            memory[addr] = value
    io = LD.CameraIO(mem_get=lambda a: [memory.get(a, 0)], mem_set=put)
    assert io.write(0x1000, 7) and writes == [(0x1000, 7)] * 2


def test_post_write_failure_rolls_back_the_uncertain_word():
    class PostWriteFailure(LD.FakeIO):
        tripped = False
        def write(self, addr, value):
            changed = super().write(addr, value)
            if addr == PL.CTRL_CAP and not self.tripped:
                self.tripped = True
                raise LD.WriteFailed("寫入完成但讀回失敗")
            return changed
    io = PostWriteFailure(IMG)
    assert offline_apply(io, image=IMG) == 1
    assert io.tripped and io.read(PL.CTRL_CAP) == stock(PL.CTRL_CAP)
    assert all(io.read(a) == stock(a) for a in HOOKS)


def test_read_retries_like_the_write_path_does():
    """讀取要和寫入一樣容忍掉包 —— 2026-09-30 四次安裝失敗的根因。

    `mem_get` 內建 4 次重試,但那一天連續四次都死在不同位址的「沒有回應」,
    而事後單獨重讀那些位址 210 次一次都沒失敗。4 次不夠。
    這條釘住「前 N-1 次全掉、第 N 次回來,read 仍要成功」。
    """
    import imx410_load as L
    calls = []

    def flaky(addr, count=1):
        calls.append(addr)
        if len(calls) < 8:
            return [None] * count
        return [0x1234ABCD] * count

    io = L.CameraIO(mem_get=flaky, mem_set=lambda *a: True,
                    sh=lambda *a: "", sync=lambda: None)
    assert io.read(0xC0000000) == 0x1234ABCD
    assert len(calls) == 8, len(calls)


def test_read_still_gives_up_eventually():
    """一直掉就要拋 —— 不能無限重試把安裝掛死。"""
    import imx410_load as L
    n = []
    io = L.CameraIO(mem_get=lambda a, c=1: (n.append(a), [None] * c)[1],
                    mem_set=lambda *a: True, sh=lambda *a: "",
                    sync=lambda: None)
    try:
        io.read(0xC0000000)
    except L.ReadFailed:
        assert len(n) == 10, len(n)
        return
    raise AssertionError("一直掉包竟然沒有拋")


def _run():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in fns:
        try:
            f()
            print(f"  ok   {n}")
        except AssertionError as e:
            bad += 1
            print(f"  FAIL {n}: {e}")
    print(f"\n{len(fns) - bad}/{len(fns)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_run())
