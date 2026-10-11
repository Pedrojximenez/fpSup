#!/usr/bin/env python3
"""看被位移的 CinemaDNG,其被截掉的尾巴是不是還躺在檔案的配置空間裡。

每格檔案 1,434,624 bytes,但 exFAT 以 512 KB 叢集配置,實際佔 3 叢集 =
1,572,864 bytes,EOF 之後有 138,240 bytes 的餘裕。若寫入端是「從位移處寫滿
整份長度」,被推出去的 7,168 / 65,536 bytes 就在那段餘裕裡。

不能用 truncate 去看 —— 檔案系統延伸邏輯長度時會補零(而且會把原本的內容蓋掉)。
正確做法:用 F_LOG2PHYS_EXT 把檔案映射到實體位移,再直接讀原始裝置。

    ./slackprobe.py <dng>            只做映射(不需要 root)
    sudo ./slackprobe.py <dng> <raw> 映射 + 讀碟,例如 raw = /dev/rdisk5s1
"""
import sys, os, fcntl, struct

F_LOG2PHYS_EXT = 65


def map_phys(path, offset=0, length=1 << 20):
    fd = os.open(path, os.O_RDONLY)
    try:
        buf = struct.pack("<Iqq", 0, length, offset)      # flags, contigbytes, devoffset
        out = fcntl.fcntl(fd, F_LOG2PHYS_EXT, buf)
        _, contig, dev = struct.unpack("<Iqq", out)
        return dev, contig
    finally:
        os.close(fd)


path = sys.argv[1]
size = os.path.getsize(path)
with open(path, "rb") as h:
    shift = h.read(70000).find(b"II*\x00")
dev, contig = map_phys(path)
print(f"{os.path.basename(path)}")
print(f"  檔案 {size} bytes   DNG 位移 {shift}")
print(f"  實體位移 0x{dev:X}   連續 {contig} bytes")
if shift <= 0:
    print("  這一格沒有位移,不用看")
    sys.exit()
if contig < size + shift:
    print(f"  ★ 連續區只有 {contig},不足 {size + shift},映射不夠用")
    sys.exit()

if len(sys.argv) < 3:
    print("  (要讀碟請加上原始裝置並用 sudo)")
    sys.exit()

raw = sys.argv[2]
with open(raw, "rb") as h:
    h.seek(dev + size)
    tail = h.read(shift)
nz = sum(1 for b in tail if b)
print(f"  EOF 之後 {shift} bytes:非零 {nz} 個 ({100*nz/len(tail):.1f}%)")
print(f"  前 32 bytes: {tail[:32].hex()}")
print("  ★ 尾巴還在,可以完整救回" if nz else "  尾巴是零 —— 真的沒寫進去,只能用 cdng_fix 折衷")
