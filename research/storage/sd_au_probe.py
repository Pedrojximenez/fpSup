"""Read-only: does the SD card support CMD20, and what AU geometry does the FS see?

Reads memory only (mem get through the USB shell). Never call while recording or
during playback; after a take, wait 10 s before running.

Addresses (fp Ver.5.02, static, see research/storage/notes/WRITE_PATH_AFTER_BULK.md):
  volume table   0xC37D066C + idx*0x4A68   (C0644B68; SD = idx 1, SSD = idx 3)
  SCR CMD_SUPPORT byte  0xC381B52B + [0xC381B4C0]*8, low 3 bits (C066C5D0; bit0 = CMD20)
  vol+0x1FF0  AU mode: 0 = AU allocation usable, 1 = fallback (C064AD18)
  vol+0x1FEC  clusters per AU        vol+0x1FE8  AU count + 2
  vol+0x1FE4  free-AU cursor/count   vol+0x146C  cluster bytes (inferred)
  vol+0x4828  bulk threshold (0 when no take is open)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'fpSup', 'fp_usb_shell'))
from putfile import mem_get  # noqa: E402

VOL_BASE, VOL_SIZE = 0xC37D066C, 0x4A68
FIELDS = [(0x1434, 'base lo'), (0x1438, 'base hi'), (0x1458, 'data start sector?'),
          (0x145C, 'cluster count?'), (0x1460, '?'), (0x146C, 'cluster bytes?'),
          (0x1FDC, '1FDC'), (0x1FE0, '1FE0'), (0x1FE4, 'free AU'), (0x1FE8, 'AU count+2'),
          (0x1FEC, 'clusters/AU'), (0x1FF0, 'AU mode'), (0x1FF4, '1FF4'), (0x4828, 'bulk threshold')]


def word(addr):
    v = mem_get(addr, 1)
    if not v or v[0] is None:
        raise SystemExit(f'read failed at {addr:#x}')
    return v[0]


def main():
    slot = word(0xC381B4C0)
    a = 0xC381B52B + slot * 8
    w = word(a & ~3)
    scr = (w >> (8 * (a & 3))) & 0xFF
    print(f'SD slot {slot}  SCR byte {scr:#04x}  CMD_SUPPORT={scr & 7:#x}  CMD20 {"YES" if scr & 1 else "no"}')
    for idx, name in ((1, 'SD'),):
        vol = VOL_BASE + idx * VOL_SIZE
        print(f'--- vol[{idx}] {name} @ {vol:#x}')
        for off, label in FIELDS:
            print(f'  +{off:#06x} {label:18s} {word(vol + off):#010x}')


if __name__ == '__main__':
    main()
