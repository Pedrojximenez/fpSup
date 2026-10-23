#!/usr/bin/env python3
"""Cost model of the CinemaDNG write path, fitted to the rec logs (WP §4).

Per file:   transfer  t_x = padded_bytes / R          (R = media rate during a batch)
            CPU       c_f  (open/alloc/close, same on SD and SSD)
            meta I/O  m_f  (small directory/FAT/bitmap writes; SD only, queue depth 1)
Stock (serial, one batch at a time, CPU+meta not overlapped with DMA):
            per file = c_f + m_f + t_x
Variants change which terms overlap or shrink.  Units: bytes, seconds, MB = 1e6.

Fit (rec logs, padding assumed to be transferred -- WP §11.2 #6, unverified):
  SD UHS-II  M12 119.88p: 57 files x 1,179,648 B in 254 ms, gap 211 ms
  SSD        M12 239.76p: 43 files x 1,572,864 B in 164 ms, gap  22 ms
"""
import math

def pad(p, c):
    return math.ceil(p / c) * c

SD_R  = 57 * 1_179_648 / 0.254          # ~264.7 MB/s
SSD_R = 43 * 1_572_864 / 0.164          # ~412.4 MB/s
C_F   = 0.022 / 43                      # SSD gap per file: CPU only, ~0.51 ms
# SD_M was fitted as 0.211/57 - C_F = 3.19 ms.  WRONG (2026-10-14): those SD takes were not backlogged --
# the batch period equals 57 frames / fps, so the gap is waiting for frames, and during recording the FS
# runs with sync off (vol+0x481C = 0, EXFAT_PER_FILE_METADATA.md), so per-file metadata I/O is ~0.
SD_M  = 0.0

MEDIA = {
    'SD UHS-II': dict(R=SD_R,  m=SD_M, cluster=128 * 1024),
    'SSD':       dict(R=SSD_R, m=0.0,  cluster=512 * 1024),
}

FORMATS = {   # file bytes (header + RAW), fps
    'M12 1008x672 12b 119.88': (1_095_168, 120000 / 1001),
    'M12 1008x672 12b 239.76': (1_095_168, 240000 / 1001),
    'FHD 12b 29.97':           (3_244_544, 30000 / 1001),
    'FHD 12b 59.94':           (3_244_544, 60000 / 1001),
    'UHD 12b 23.976':          (8_447_488, 24000 / 1001),
}

# Each variant returns seconds per file.
def stock(p, md, cl):        return C_F + md['m'] + pad(p, cl) / md['R']
def overlap(p, md, cl):      return max(C_F, md['m'] + pad(p, cl) / md['R'])          # CPU hidden; SD meta I/O cannot overlap
def meta_batched(p, md, cl): return C_F + 0.1e-3 * bool(md['m']) + pad(p, cl) / md['R']  # one dir write per block
def both(p, md, cl):         return max(C_F, 0.1e-3 * bool(md['m']) + pad(p, cl) / md['R'])

VARIANTS = [('stock', stock), ('overlap', overlap), ('meta batched', meta_batched), ('overlap+meta', both)]


def table(cluster_override=None):
    for mname, md in MEDIA.items():
        cl = cluster_override or md['cluster']
        print(f'\n== {mname}  R={md["R"]/1e6:.0f} MB/s  cluster={cl//1024} KiB  m_f={md["m"]*1e3:.2f} ms  c_f={C_F*1e3:.2f} ms')
        print(f'{"format":26s} {"need":>6s} ' + ' '.join(f'{n:>13s}' for n, _ in VARIANTS))
        for fname, (p, fps) in FORMATS.items():
            need = p * fps / 1e6
            cells = []
            for _, f in VARIANTS:
                rate = p / f(p, md, cl) / 1e6
                cells.append(f'{rate:7.0f}{" ok" if rate >= need else " --":>3s}   ')
            print(f'{fname:26s} {need:6.0f} ' + ' '.join(cells))


def slots_needed(p, fps, rate, block, stall):
    """Frames in flight: one block filling + one writing + whatever arrives during a stall."""
    t_block = block / rate
    return math.ceil(fps * (2 * t_block + stall))


if __name__ == '__main__':
    # Sanity: the model must reproduce the measured stock rates.
    # SD 120p was not backlogged (sustained = need), so only the SSD 240p take checks the model.
    for mname, p, cl, measured in (('SSD', 1_095_168, 512 * 1024, 250),):
        md = MEDIA[mname]
        print(f'check {mname}: model {p / stock(p, md, cl) / 1e6:.0f} MB/s vs measured ~{measured}')
    table()
    print('\n--- SSD reformatted to 128 KiB clusters ---')
    MEDIA_SSD = {'SSD': MEDIA['SSD']}
    saved = dict(MEDIA); MEDIA.clear(); MEDIA.update(MEDIA_SSD); table(128 * 1024); MEDIA.clear(); MEDIA.update(saved)
    print('\n--- frames in flight (2 blocks + stall), stock pool has 94 usable ---')
    for fname, (p, fps) in FORMATS.items():
        for block in (64 << 20, 32 << 20, 8 << 20):
            n = slots_needed(p, fps, p * fps * 1.15, block, 0.2)
            print(f'{fname:26s} block {block >> 20:2d} MiB  stall 200 ms  -> {n:4d} frames')
