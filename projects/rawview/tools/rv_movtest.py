#!/usr/bin/env python3
"""rv_movtest.py — MOV 錄影凍結的分段測試(README「MOV 錄影凍結」)。

    python3 rv_movtest.py A        只開 hook A(待機用錄影增益);B 點維持原指令;不換 tone 表
    python3 rv_movtest.py AB       hook A + B(RAW_CORR 1×);不換 tone 表
    python3 rv_movtest.py ABT      A + B + tone 表(= 完整 RAW 模式)

每一段:安裝／設定 → ISO 640→800 讓增益重算 → 印狀態 → 錄約 0.5 秒 MOV → 每 2 秒查一次是否停止 → 列出最新片段。
凍結時 shell 會回 LIBUSB_ERROR_TIMEOUT;那就關機重開,並記下是哪一段。
"""
import sys, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import rv_raw as R
from putfile import sh


def pulse():
    sh('key MOVON', retries=0); time.sleep(0.12); sh('key MOVOFF', retries=0)


def main(stage):
    if R.word(R.SITES['A'][0]) == R.SITES['A'][1]:
        R.install()
    p = R.block()
    siteB, origB, nameB = R.SITES['B']
    if 'B' in stage:
        R.set_word(siteB, R.bl(siteB, p + R.sym(p)[nameB]))
    else:
        R.set_word(siteB, origB)
    R.publish()
    if stage == '0':                      # 原廠行為:旗標 0、原廠 tone 表
        R.set_word(p, 0)
        R.set_word(R.ROOT_P70, R.ROOT_P70_ORIG)
        R.mem_set(R.KEY_CTX0, 0xFFFFFFFF)
    elif 'T' in stage:
        if R.word(p + 8) == 0:
            L = R.layout()
            head = (R.HERE.parent / 'curves' / 'tone2048_iso100.u16le').read_bytes()[:64]
            got = b''.join(x.to_bytes(4, 'little') for x in R.mem_get(L['tabs'], 16))
            if got == head:                   # 表還在 pool:只寫回參數,不重傳
                R.set_word(p + 8, L['tabs'])
                R.set_word(p + 0xC, L['slots'])
            else:
                R.load()
        R.on()
    else:
        R.set_word(R.ROOT_P70, R.ROOT_P70_ORIG)
        R.set_word(p + 8, 0)              # tab_base 0 → hook A 只改增益、不換表
        R.set_word(p, 1)
    sh('menu SetIso 640'); time.sleep(1.5); sh('menu SetIso 800'); time.sleep(2)
    print(f'== stage {stage}')
    R.status()
    pulse(); time.sleep(0.5); pulse()
    for i in range(4):
        time.sleep(2)
        try:
            print(f't+{2 * i + 2}s', sh('status get is_recording', retries=0).strip())
        except Exception as e:  # noqa: BLE001
            print('ERR', e)
    print('\n'.join([l for l in sh(r'dir \CINEMA').splitlines() if l.strip()][-2:]))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'A')
