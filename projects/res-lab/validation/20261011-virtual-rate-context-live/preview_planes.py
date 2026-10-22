"""Bounded native preview publication reads; caller owns the camera lease.

These fixed BSS ranges are published by ROM C01D1630, C01D69D0 and C01D7248
(out/decomp/full/blk_c01.c). No pointer is dereferenced. Native mem get copies
the words through the existing shell; no scratch, ARM injection or MEM1 DMA.
Four independent reads are NOT an atomic snapshot or DMA ownership proof.
The largest reply is 64 words, below the running worker's 16 KiB CAP_MAX.
"""
GROUPS = (
    ('engine_and_geometry', 0xC31DF574, 14),
    ('plane_routes', 0xC31DF8E4, 5),
    ('plane0_and_plane1', 0xC31E10F4, 61),
    ('consumer0_and_consumer1', 0xC30254B4, 64),
)


def read_planes(mem_get, clock, phase):
    result = {'phase': phase, 'groups': {},
              'limitation': 'Independent fixed BSS reads, not an atomic snapshot or DMA ownership proof.'}
    for name, address, count in GROUPS:
        begin = clock.mark('plane_read_begin', phase=phase, group=name,
                           address=hex(address), count=count)
        words = mem_get(address, count, tries=1)
        assert len(words) == count and all(isinstance(w, int) for w in words)
        end = clock.mark('plane_read_end', phase=phase, group=name, words=words)
        result['groups'][name] = {'address': hex(address), 'words': words,
                                  'begin_sequence': begin['sequence'],
                                  'end_sequence': end['sequence']}
    return result
