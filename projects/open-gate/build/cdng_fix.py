#!/usr/bin/env python3
"""把 HSW 錄出來的 CinemaDNG 切齊 —— 有些格子的 DNG 在檔案裡被往後推了。

2026-09-21 在 A001_148(4232 格、180 fps、SSD)上量到:

    位移 0       1236 格 (29.2%)   正常
    位移 7168    1417 格 (33.5%)   = 0x15400(保留標頭量) − 0x13800(實際標頭)
    位移 65536   1579 格 (37.3%)   = 64 KB

檔案總長固定 1,434,624,所以被推出去的那一段等於從尾巴被截掉。修法是把前導的
零切掉、尾端補零補回原長 —— DNG 的 StripOffsets(79,872) + StripByteCounts
(1,354,752) 才會落在檔案裡,達芬奇才讀得動。代價是影像最後幾行是黑的:

    位移 7168   -> 少 3.5 行 / 672
    位移 65536  -> 少 32 行 / 672

冪等:修過的檔案位移是 0,再跑一次不會動它。

    ./cdng_fix.py <clip 目錄> [--apply]
"""
import os, sys, glob, tempfile

MAGIC = b"II*\x00"


def scan(path):
    with open(path, "rb") as h:
        d = h.read()
    return d, d.find(MAGIC), len(d)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    apply_ = "--apply" in sys.argv
    if not args:
        raise SystemExit(__doc__)
    for clip in args:
        files = sorted(glob.glob(os.path.join(clip, "*.DNG")))
        hist, fixed, bad = {}, 0, []
        for f in files:
            d, off, size = scan(f)
            hist[off] = hist.get(off, 0) + 1
            if off < 0:
                bad.append(f)
                continue
            if off == 0:
                continue
            if apply_:
                out = d[off:] + b"\x00" * off          # 切前導、補尾端,長度不變
                assert len(out) == size
                fd, tmp = tempfile.mkstemp(dir=clip, suffix=".tmp")
                with os.fdopen(fd, "wb") as h:
                    h.write(out)
                os.replace(tmp, f)
            fixed += 1
        name = os.path.basename(clip.rstrip("/"))
        dist = ", ".join(f"{k}:{v}" for k, v in sorted(hist.items()))
        print(f"{name:<12} {len(files):>5} 格   位移分布 {{{dist}}}"
              + (f"   -> 已修 {fixed}" if apply_ else f"   需修 {fixed}")
              + (f"   ★ 無標頭 {len(bad)}" if bad else ""))


if __name__ == "__main__":
    main()
