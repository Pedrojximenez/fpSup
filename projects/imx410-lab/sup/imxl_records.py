"""IMXL capture memory -> records (shared by the host tool and test_card.py).

The sink fills the lent chunks front to back with no gaps, so their
concatenation is one stream:  [ix_rec 32 B][bytes of data][pad to 4] ...
ix_rec = magic "IXR1", seq, cl, bytes, ncookie, t_us, copy_us, nseg.
A record's data is exactly what ULWR would have written to the card starting
at cluster `cl`: whole DNG files, each padded to a cluster.
"""
import struct

REC_MAGIC = 0x31525849          # "IXR1"
CAP_MAGIC = 0x4C584D49          # "IMXL"
REC = struct.Struct('<8I')
FIELDS = ('magic', 'seq', 'cl', 'bytes', 'ncookie', 't_us', 'copy_us', 'nseg')

# ix_cap, mirrored from ix_wr.h (version 1)
CAP_HEAD = ('magic', 'version', 'mode', 'nchunk')
MAX_CHUNK = 32
CAP_TAIL = ('ci', 'coff', 'used', 'n_rec', 'n_full', 'n_discard', 'n_sd',
            't_first', 't_last', 'copy_us', 'copy_max_us')
O_CHUNK = 16
O_TAIL = O_CHUNK + 8 * MAX_CHUNK
CAP_BYTES = O_TAIL + 4 * len(CAP_TAIL)
MODES = {'sd': 0, 'capture': 1, 'discard': 2}


def parse_cap(raw):
    """ix_cap bytes -> dict (chunks as a list of (addr, len))."""
    d = dict(zip(CAP_HEAD, struct.unpack_from('<4I', raw, 0)))
    d['chunks'] = [struct.unpack_from('<2I', raw, O_CHUNK + 8 * i) for i in range(MAX_CHUNK)]
    d.update(zip(CAP_TAIL, struct.unpack_from(f'<{len(CAP_TAIL)}I', raw, O_TAIL)))
    return d


def records(stream, used):
    """Yield one dict per record in stream[:used]; raises on a broken chain."""
    pos = 0
    while pos < used:
        if used - pos < REC.size:
            raise ValueError(f'truncated header at {pos}')
        r = dict(zip(FIELDS, REC.unpack_from(stream, pos)))
        if r['magic'] != REC_MAGIC:
            raise ValueError(f'bad magic {r["magic"]:#x} at {pos}')
        start = pos + REC.size
        r['data'] = bytes(stream[start:start + r['bytes']])
        if len(r['data']) != r['bytes']:
            raise ValueError(f'record {r["seq"]} runs past the end')
        pos = start + ((r['bytes'] + 3) & ~3)
        yield r
    if pos != used:
        raise ValueError(f'records end at {pos}, sink says {used}')


def disk_image(recs, heap_lba, spc, sector=512):
    """{byte offset on the medium: data}, as ULWR would have laid it down."""
    return {((r['cl'] - 2) * spc + heap_lba) * sector: r['data'] for r in recs}
