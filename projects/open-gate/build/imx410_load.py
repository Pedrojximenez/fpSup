#!/usr/bin/env python3
"""IMX410 全功能版的舊 USB 載入器。

2026-10-04 安全停用:這份計畫會把 Sensor Lab 固定寫進 stage2 不還原的
cave,包含已有原廠資料的字。所有入口(檢查、分段、解除後安裝)先離線驗證
計畫;目前一律在開啟相機傳輸前拒絕。保留舊狀態機供 FakeIO 離線回歸測試。

照 og3k_load.py 的紀律寫:只接受**完整**狀態,任何部分安裝、掉寫或未知
hook 都零寫入停下來,失敗一律 rollback。多一件事 —— 它認得「相機上正跑著
另一個產品」,而且可以把那個產品解除掉。

    ./imx410_load.py --check     只快照與分類,零寫入
    ./imx410_load.py             從全原廠狀態安裝
    ./imx410_load.py --disarm    先把別的產品解除成原廠,再安裝

★ 為什麼需要 --disarm:2026-09-28 相機上跑著一套完整的 OG3K(14 個 hook 有
  13 個武裝),而它的 payload 槽與本版**正面衝突**。逐字覆寫一段被 hook 指著、
  每秒執行幾十次的 payload,就是 2026-09-12 相機當場當掉的那個動作。

★ 解除的位址集合**不是手列的** —— 直接從 og3k_plan 自己的計畫推導,對每個
  目標算一次。手列一定會漏,而漏掉的那一個就是留在相機上的髒狀態。

★ 最壞情況:寫壞了是凍結 -> 拔電池 -> 卡上的產品回來、shell 也回來。
  不需要實體換卡。(換 fpSup.BIN 的最壞情況是開不了機而且沒有 shell。)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))

import imx410_plan as PL
import res_lab_cave_audit as CAVE_AUDIT

B = 0xC0000000
# 私有 cave:這一段是我們自己的,寫它不影響任何原廠功能,所以先寫。
PRIVATE_LO, PRIVATE_HI = 0xC0730000, 0xC0732C84
OTHER_TARGETS = ("og3k", "og2k", "og6k", "hsw")


class ReadFailed(Exception):
    pass


class WriteFailed(Exception):
    pass


class CameraIO:
    """走 USB shell 的 mem get / mem set。寫入一律讀回。

    ★ `mem_get` 回傳的是 **list**,而且沒回來的字是 `None` —— 不是 int。
      2026-09-28 我把它當 int 用,於是每一次 `!=` 都是 `list != int` 恆真:
      分類器永遠說 foreign、「72 個髒位址」其實只是 foreign 集合的大小。
      離線的 FakeIO 回傳 int,所以測試全過也抓不到。
      `test_camera_io_unwraps_mem_get` 用 stub 直接釘住這個契約。
    """

    def __init__(self, mem_get=None, mem_set=None, sh=None, sync=None):
        if mem_get is None:
            from putfile import mem_get, mem_set, sh   # noqa: PLW0127
        self._get, self._set, self._sh = mem_get, mem_set, sh
        self._sync = sync

    def read(self, addr, tries=10):
        """讀一個字。掉包就重試 —— 讀取是冪等的。

        ★ 2026-09-30:這裡原本只有 `mem_get` 內建的 4 次重試,而寫入那側
          早就重試 3 次、註解還寫著「一次掉包不該讓整次安裝失敗」——
          **讀取沒有跟上**。`og3k_load.rd()` 重試 10 次(合計最多 40 次),
          這裡對齊它。

          當天連續四次安裝失敗,每次都死在不同位址的「沒有回應」,
          而事後單獨重讀那些位址 210 次一次都沒失敗 —— 4 次不夠而已。
        """
        last = None
        for _ in range(tries):
            try:
                got = self._get(addr)
            except Exception as e:                   # noqa: BLE001
                last = e
                continue
            v = got[0] if isinstance(got, (list, tuple)) else got
            if v is not None:
                return v
        if last is not None:
            raise ReadFailed(f"0x{addr:08X}: {last}") from last
        raise ReadFailed(f"0x{addr:08X}: 沒有回應({tries} 次)")

    def read_many(self, addr, count):
        """一次讀多個字,掉的那幾個逐字補讀。

        ★ 批次讀**會掉包**。2026-09-28 兩次快照分別掉在 0xC0731508 與
          0xC0BE1918 —— 同一份程式碼、不同位址,所以不是某一格有問題,
          是大回覆本身不可靠。`og3k_load` 一次只讀一個字,那是對的;
          批次只是加速,不能拿它當正確性的基礎。
        """
        try:
            got = list(self._get(addr, count))
        except Exception:                            # noqa: BLE001
            got = [None] * count
        if len(got) > count:
            raise ReadFailed(f"0x{addr:08X}: 回覆 {len(got)} 字超過要求 {count}")
        got += [None] * (count - len(got))
        for i, v in enumerate(got):
            if v is None:
                got[i] = self.read(addr + i * 4)     # 逐字補,它自己會重試
        return got

    def write(self, addr, value, tries=3):
        """寫一個字並讀回。掉包就重試 —— **記憶體寫入是冪等的**。

        2026-09-28 第一次安裝在 0xC0730614 停下:寫入本身沒問題(事後單獨寫
        0xFFFFFFFF 完全正常),是驗證的那次讀掉了包。`mem_get` 自己已經重試
        四次還是空的 —— putfile 的 docstring 就寫著「整個命令有時會在任一
        方向消失」。一次掉包不該讓整次安裝失敗。

        重試的是「寫同一個值到同一個位址」,不是別的動作,所以安全。
        """
        last = None
        for _ in range(tries):
            try:
                if self.read(addr) == value:
                    return last is not None      # 重試時第一次可能已經寫進去了
            except ReadFailed as e:
                last = e
                continue
            self._set(addr, value)
            try:
                if self.read(addr) == value:
                    return True
                raise WriteFailed(f"0x{addr:08X} 讀回不符")
            except (ReadFailed, WriteFailed) as e:
                last = e
        raise WriteFailed(f"0x{addr:08X} 重試 {tries} 次仍無法確認:{last}")

    def sync(self):
        """把剛寫的程式碼發布出去:先清 D-cache,再讓 I-cache 失效。

        ★ 2026-09-28 第一次上機就死在這裡。我原本自己發明了一個 shell 指令來
          呼叫韌體常式 —— **shell 沒有那個指令**(回 `not found cmd ...`),
          而我連回覆都沒看。於是 1295 個字的新程式碼從來沒有發布到 I-cache,
          picker hook 一掛,CPU 就跳進舊的快取行執行,相機當場凍結。

          shell 呼叫韌體常式的正確做法是**暫時借用 echo 的處理函式**,
          og3k_load.call_firmware_noargs 已經做好而且驗證過(它還會強制把
          echo slot 還原)。直接用它,不要自己再寫一份。
        """
        if self._sync is not None:
            self._sync()
            return
        from og3k_load import sync_code
        sync_code()


class FakeIO:
    """離線測試用。用映像當底,記錄每一次寫入。"""

    def __init__(self, image, overrides=None):
        self.img = image
        self.mem = dict(overrides or {})
        self.writes = []
        self.synced = 0
        self.fail_at = None

    def _stock(self, addr):
        return int.from_bytes(self.img[addr - B: addr - B + 4], "little")

    def read(self, addr):
        return self.mem.get(addr, self._stock(addr))

    def write(self, addr, value):
        # **一次性**失敗。模擬的是「掉了一次寫入」,不是「連線死了」——
        # 後者連 rollback 都做不到,測不出 rollback 對不對。
        if self.fail_at is not None and len(self.writes) >= self.fail_at:
            self.fail_at = None
            raise WriteFailed(f"注入的失敗 @0x{addr:08X}")
        if self.read(addr) == value:
            return False
        self.mem[addr] = value
        self.writes.append((addr, value))
        return True

    def sync(self):
        self.synced += 1


def _other_plan(target):
    """另一個產品的計畫。它在 import 時讀 OG_TARGET,所以要另開行程。"""
    src = ("import sys;sys.path.insert(0,'.');import og3k_plan as P,json;"
           "print(json.dumps([[a,v] for a,v,_ in P.plan()]))")
    r = subprocess.run([sys.executable, "-c", src], cwd=str(HERE),
                       capture_output=True, text=True,
                       env={**os.environ, "OG_TARGET": target})
    if r.returncode:
        raise SystemExit(f"讀 {target} 的計畫失敗:{r.stderr[-400:]}")
    import json
    return {a: v for a, v in json.loads(r.stdout)}


def foreign_addresses():
    """別的產品會寫、而且**不在我們私有 cave 裡**的每一個位址。

    這些是「解除」時要還原成原廠的東西 —— cave 裡的殘留無所謂(沒有人指著
    它,而且我們馬上會蓋過去),但選單 CSV、控制器上限、donor 的時序記錄
    那些**原廠資料**留著就是髒狀態。
    """
    out = set()
    for t in OTHER_TARGETS:
        out |= {a for a in _other_plan(t) if not (PRIVATE_LO <= a < PRIVATE_HI)}
    return out


def _stock_word(img, addr):
    return int.from_bytes(img[addr - B: addr - B + 4], "little")


def classify(snapshot, desired, hook_sites, stock, dirty):
    """相機現在是什麼狀態。

    ★ **不能只看 hook 的值。** 我們刻意重用 og3k 的 payload 槽,所以好幾個
      hook 的分支字與 og3k 逐位元相同(picker、畫布、sel、name、fmt、out、
      gs、fps 都是)。只比 hook 會把「跑著完整 OG3K」誤判成「我們裝一半」,
      然後在 hook 還武裝著的狀態下去覆寫它的 payload —— 那正是會凍結的動作。
      所以判「已安裝」要**整份計畫逐字相符**。
    """
    if all(snapshot[a] == desired[a] for a in desired):
        return "installed"
    # 「乾淨」= 每一個字要嘛是原廠、要嘛已經是我們要寫的值。分段武裝
    # (--stage)會停在這個狀態:前幾階段的 hook 掛著、後面的還是原廠。
    # 這樣分段安裝才是冪等的,不必每一階段都先 --disarm。
    if not dirty and all(snapshot[a] == stock[a] for a in desired):
        return "stock"
    if all(snapshot[a] in (stock[a], desired[a]) for a in desired) and not dirty:
        return "clean"
    # 其餘一律當「不是我們的、也不乾淨」。證不出來就不要賭,
    # 要往下走只能明確帶 --disarm 把全部拆回原廠。
    return "foreign"


def _preflight_safe_plan(items):
    """Reject unjournaled stock writes and every fixed Sensor Lab cave word.

    Read the pinned firmware image here, independent of a caller's ``image``
    argument.  This runs before CameraIO is constructed or any transport I/O.
    """
    stock_image = PL.FIRMWARE.read_bytes()
    CAVE_AUDIT.assert_pristine_cave_plan(items, stock_image)
    CAVE_AUDIT.assert_no_res_lab_static_cave_plan(items)


def apply(io=None, *, check=False, disarm=False, image=None, stage=None,
          axis=None):
    """stage=None 全裝;stage=N 只武裝前 N 個階段(body 一律全寫)。

    ★ `axis`:用哪一組七軸當**安裝時**的初始軸。這不只是「開機停在哪一組」——
      `CG_BIN` / `CG_FILL` / `CG_WINDOW` 仍由安裝時決定。
      `CG_ZOOM` / `CG_OVER60` 已在 payload 內依每次配方判斷(§12.31)。
    """
    img = image if image is not None else PL.FIRMWARE.read_bytes()

    bad = PL.layout_errors() + PL.hook_errors(img) + PL.order_errors()
    if bad:
        for b in bad:
            print("  " + b)
        print("★ 靜態檢查失敗;零寫入")
        return 1

    all_stages = PL._stages()
    if stage is not None:
        if not 0 <= stage <= len(all_stages):
            print(f"★ --stage 要在 0..{len(all_stages)} 之間")
            return 1
        items = PL.plan(recipe_axis=axis, stages=all_stages[:stage])
        print("  階段:" + (", ".join(n for n, _ in all_stages[:stage]) or "只寫 body"))
    else:
        items = PL.plan(recipe_axis=axis)
    desired = {a: v for a, v, _ in items}
    if len(desired) != len(items):
        dup = len(items) - len(desired)
        print(f"★ 計畫有 {dup} 個重複位址;零寫入")
        return 1

    try:
        _preflight_safe_plan(items)
    except ValueError as e:
        print(f"★ Sensor Lab 計畫不安全;零相機 I/O:{e}")
        return 1

    io = io or CameraIO()

    hook_sites = [a for a, _, n in items if "hook" in n]
    foreign = foreign_addresses()
    # 執行期會變的槽不參與分類 —— 它們一定會偏離初值,那是設計,不是髒。
    volatile = PL.volatile_addresses()
    watch = set(desired) | set(hook_sites) | foreign

    print("IMX410 全功能版 " + ("安全檢查" if check else "安裝") + "\n")
    try:
        snapshot = _snapshot(io, watch)
    except ReadFailed as e:
        print(f"★ 預檢讀取失敗;零寫入:{e}")
        return 1
    print(f"  預檢 {len(watch)} 個位址全部可讀")

    stock = {a: _stock_word(img, a) for a in watch}
    # 「髒」= 既不是原廠、也不是**我們要寫的值**。少了後半句,分段安裝
    # 第二階段就會把自己第一階段寫的選單 CSV 當成別人的殘留。
    dirty = sorted(a for a in foreign if a not in volatile
                   and snapshot[a] != stock[a] and snapshot[a] != desired.get(a))
    state = classify({a: v for a, v in snapshot.items() if a not in volatile},
                     {a: v for a, v in desired.items() if a not in volatile},
                     hook_sites, stock, dirty)
    print(f"  狀態:{state}    非原廠的原廠資料:{len(dirty)} 個位址")

    if state == "installed":
        print("★ 同一份已完整安裝;零寫入")
        return 0
    if state == "clean":
        print("  (前幾階段已就位,繼續)")
    if state == "foreign" and not disarm:
        print("★ 相機不是乾淨原廠,也不是本版 —— 可能跑著別的產品,或裝了一半。")
        print("  要往下走只能明確解除:")
        print("    ./imx410_load.py --disarm")
        print("    (最壞情況是凍結 -> 拔電池 -> 卡上的產品回來,不用換卡)")
        return 1

    if check:
        changes = sum(snapshot[a] != desired[a] for a in desired)
        print(f"★ 可以安裝;預計改 {changes} 字"
              + (f",另外要先還原 {len(dirty)} 個原廠字" if dirty else "")
              + ";本次零寫入")
        return 0

    # ---- 解除:hook 先回原廠,再還原被動過的原廠資料 -----------------------
    # 順序不能反 —— 還活著的 hook 指著的 payload,在 hook 拆掉之前不能碰,
    # 而原廠資料(選單、時序)有些正是活著的 payload 在讀的。
    if state == "foreign":
        try:
            # **無條件拆**。hook 的值剛好等於我們要寫的那個,不代表安全 ——
            # 它底下指著的 payload 是別人的,而我們正要覆寫那塊記憶體。
            for site in hook_sites:
                io.write(site, stock[site])
            io.sync()
            for site in hook_sites:
                if io.read(site) != stock[site]:
                    raise WriteFailed(f"解除後 0x{site:08X} 仍不是原廠")
            for a in dirty:
                io.write(a, stock[a])
            io.sync()
        except Exception as e:                        # noqa: BLE001
            print(f"★ 解除失敗:{e};相機可能是半解除狀態,請拔電池")
            return 1
        print(f"  已解除:{len(hook_sites)} 個 hook 回原廠,還原 {len(dirty)} 個原廠字")
        snapshot = _snapshot(io, watch)

    # ---- 安裝:先私有 cave,最後才碰會立刻影響選單/表格的原廠資料 ---------
    body = [(a, v, n) for a, v, n in items if a not in set(hook_sites)]
    body.sort(key=lambda it: 0 if PRIVATE_LO <= it[0] < PRIVATE_HI else 1)
    touched_external: list[int] = []
    changed = 0
    try:
        for a, v, _ in body:
            # 寫入可能成功後才在讀回時拋錯;先記錄嘗試過的位址,不可漏還原。
            if not (PRIVATE_LO <= a < PRIVATE_HI):
                touched_external.append(a)
            if io.write(a, v):
                changed += 1
        io.sync()
    except Exception as e:                            # noqa: BLE001
        _rollback(io, touched_external, stock)
        print(f"★ body 寫入失敗:{e};一個 hook 都沒掛")
        return 1

    # ---- 武裝。宣告順序是依賴端先、picker 最後,不要排序。 ----------------
    try:
        for site in hook_sites:
            if io.write(site, desired[site]):
                changed += 1
        io.sync()
        for site in hook_sites:
            if io.read(site) != desired[site]:
                raise WriteFailed(f"hook verify 0x{site:08X}")
    except Exception as e:                            # noqa: BLE001
        _rollback(io, list(hook_sites) + touched_external, stock)
        print(f"★ hook commit 失敗:{e};已要求全部回原廠")
        return 1

    print(f"  計畫 {len(items)} 筆;改了 {changed} 字;payload 與 hook 都讀回過")
    print("★ 就緒(只限本次 session;換版本前拔電池)")
    return 0


def _snapshot(io, addresses, run=64):
    """讀一大堆位址。連續的併成一次 `mem get`,零散的逐字。"""
    out = {}
    rest = sorted(addresses)
    i = 0
    while i < len(rest):
        j = i
        while (j + 1 < len(rest) and rest[j + 1] == rest[j] + 4
               and j - i + 1 < run):
            j += 1
        n = j - i + 1
        if n >= 4 and hasattr(io, "read_many"):
            for k, v in enumerate(io.read_many(rest[i], n)):
                out[rest[i] + k * 4] = v
        else:
            for a in rest[i:j + 1]:
                out[a] = io.read(a)
        i = j + 1
    return out


def _rollback(io, addresses, stock):
    errs = []
    for a in addresses:
        try:
            io.write(a, stock[a])
        except Exception as e:                        # noqa: BLE001
            errs.append(f"0x{a:08X}: {e}")
    try:
        io.sync()
    except Exception as e:                            # noqa: BLE001
        errs.append(str(e))
    if errs:
        print("  回復不完整,必須拔電池:" + "; ".join(errs[:4]))
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="只分類,零寫入")
    ap.add_argument("--disarm", action="store_true",
                    help="先把別的產品解除成原廠,再安裝")
    ap.add_argument("--stage", type=int, metavar="N",
                    help="只武裝前 N 個階段(0 = 只寫 body)。"
                         "階段順序:canvas, display, fps, menu, picker")
    ap.add_argument("--axis-preset", metavar="X",
                    help="選 imx410_axis 的安裝初值;bin 模板仍由此決定。"
                         "位深與格率在原廠選單路徑以選單為準;RWZM 可執行期改。")
    a = ap.parse_args(argv)
    axis = None
    if a.axis_preset:
        from imx410_axis import PRESETS, preset_axis
        if a.axis_preset not in PRESETS:
            print(f"★ 沒有這組預設:{a.axis_preset};可用 {sorted(PRESETS)}")
            return 1
        axis, _r = preset_axis(PL.Registry(), a.axis_preset)
        print(f"  安裝時的初始軸:預設組 {a.axis_preset} = {axis}")
    return apply(check=a.check, disarm=a.disarm, stage=a.stage, axis=axis)


if __name__ == "__main__":
    sys.exit(main())
