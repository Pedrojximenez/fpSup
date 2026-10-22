#!/usr/bin/env python3
"""嚴謹版:量測某個解析度設定下,QS 的 RES. 格到底載入哪些 .xci。

    ./qsprobe.py 4        量測 enum 4 (OG3K)
    ./qsprobe.py 2 4      依序量測 FHD 與 OG3K

紀律(前一輪就是少了這些才得出錯誤結論):
  - 呼叫前必須已知 QS 是關的；兩次 toggle 只會回到原狀態，不能正規化
  - 換設定後等足夠久,讓重新解析與重繪完成
  - 清 log 之後才開 QS,量完立刻關 QS
  - 濾掉 0xc055fa14 / 0xc055fa30 的 ERR 洗版
"""
import sys, time

sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import sh

NAME_SITE, DIM_SITE = '0xc055fdf4', '0xc055fe14'


def k(cmd, wait):
    try:
        # A timeout often means the key reached the camera but its reply did
        # not.  Retrying a toggle can undo the action we wanted to measure.
        sh(cmd, retries=0)
    except Exception:
        pass
    time.sleep(wait)


def loads():
    """把 log 裡的 (檔名, 尺寸) 配對取出。"""
    out, prev = [], None
    for l in sh('log out GUI').splitlines():
        if NAME_SITE in l:
            prev = l.split(NAME_SITE + ',')[-1].strip()
        elif DIM_SITE in l and prev is not None:
            out.append((prev, l.split(DIM_SITE + ',')[-1].strip().rstrip(',')))
            prev = None
    return out


def probe(enum):
    # 關鍵紀律:換狀態後的「第一次繪製」會帶著舊狀態的內容(跨幀污染),
    # 所以先畫一次丟掉,清 log,再畫第二次才是乾淨的。
    sh(f'menu SetMovRecSize {enum}')
    time.sleep(3.0)               # 等重新解析
    k('key QSON', 1.5)            # 第一次繪製 —— 丟掉
    k('key QSON', 1.0)            # 關
    sh('log clear')
    k('key QSON', 1.5)            # 第二次繪製 —— 這一幀才算數
    got = loads()
    k('key QSON', 1.0)            # 關回去
    res = [
        x for x in got
        if 'resolution' in x[0].lower()
        or x[0].upper().startswith(('OG3K_', 'FP3K_'))
    ]
    print(f"  enum {enum}: 這一幀 {len(got)} 張")
    for n, dm in res:
        print(f"     {n:34s} {dm}")
    if not res:
        print("     (完全沒有 resolution 相關)")
    return [n for n, _ in res]


def main():
    sh('gui image log 1')
    sh('log act GUI')
    for a in sys.argv[1:] or ['4']:
        probe(int(a))
    print("  shell:", sh('version')[:22].replace('\n', ' '))


main()
