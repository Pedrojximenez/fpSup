#!/usr/bin/env python3
"""rv_floortest.py — 預覽色調表在第 0/1 格之間是否內插(最底 1.6 檔看不看得到)。

    python3 rv_floortest.py arm      # 備份使用中表的前 32 格,改成 [0] = 黑、[1..31] = 白,強制重載
    python3 rv_floortest.py restore  # 寫回備份,強制重載,讀回核對

判讀:暗處從黑到白是平滑漸層 → 查表有內插(或上游精度 > 11 bit),最底 1.6 檔有進預覽;
     只有純黑/純白兩種(雜訊呈黑白顆粒) → 沒有內插,這段只剩一階。
使用中的表 = 0xC3414470 + 0xA0 指向的位址(rv_card.status 同一處);表是 u16 × 2048。
強制重載:把 params+0x0C(last_rel)清 0 → stub_gs 下次增益計算重寫插槽並清 KEY_CTX0。
"""
import json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rv_card import params, word, status  # noqa: E402
from putfile import mem_set               # noqa: E402

N = 16                       # 16 words = 32 格
WHITE = 8170
BACKUP = HERE.parent / 'captures' / 'floortest_backup.json'


def active():
    a0 = word(0xC3414470 + 0xA0)
    p = params()
    tab = word(p + 0x10)
    if not tab <= a0 < tab + 62 * 0x1000:
        raise SystemExit(f'使用中的表 0x{a0:08X} 不是 rawview 的表(RAW 沒生效?)')
    return p, a0


def reload(p):
    mem_set(p + 0x0C, 0)
    time.sleep(1.5)


def arm():
    p, a0 = active()
    if BACKUP.exists():
        raise SystemExit(f'{BACKUP} 已存在:先 restore')
    orig = [word(a0 + 4 * i) for i in range(N)]
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps({'addr': a0, 'words': orig}))
    print(f'表 0x{a0:08X} 前 {2 * N} 格已備份:[0]={orig[0] & 0xFFFF} [1]={orig[0] >> 16} [2]={orig[1] & 0xFFFF}')
    mem_set(a0, 0 | WHITE << 16)
    for i in range(1, N):
        mem_set(a0 + 4 * i, WHITE | WHITE << 16)
    bad = [i for i in range(N) if word(a0 + 4 * i) != (WHITE << 16 if i == 0 else WHITE | WHITE << 16)]
    if bad:
        raise SystemExit(f'寫入未生效:word {bad}(執行 restore)')
    reload(p)
    print('已改:[0] = 黑、[1..31] = 白,已強制重載')


def restore():
    b = json.loads(BACKUP.read_text())
    a0, orig = b['addr'], b['words']
    for i, w in enumerate(orig):
        mem_set(a0 + 4 * i, w)
    bad = [i for i, w in enumerate(orig) if word(a0 + 4 * i) != w]
    if bad:
        raise SystemExit(f'還原未完成:word {bad}(再執行一次 restore)')
    reload(params())
    BACKUP.unlink()
    print(f'表 0x{a0:08X} 已還原並讀回核對')
    status()


if __name__ == '__main__':
    {'arm': arm, 'restore': restore}[sys.argv[1]]()
