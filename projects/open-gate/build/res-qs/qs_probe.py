"""The original NBU interpreter (FUN_c05e6400) over a whole QS_CINE-sized page.

sl_b25_page.native_parse with room: QS_CINE is 1.2 MB and 955 objects, so the
probe's synthetic RAM grows to 16 MiB (heap and stack follow).  Same fixed
construction allow-list as the B2_5 page.  Offline only."""
from __future__ import annotations

import qs_page as Q

P, N, U = Q.P, Q.N, Q.U


def native_parse(page: bytes, pool: bytes, img: bytes):
    import nbu_probe as NP

    class QsProbe(NP.NbuProbe):
        RAM_SIZE = 0x1000000
        BLOB_MAX = (len(page) + 0xFFFF) & ~0xFFFF
        HEAP = (NP.NbuProbe.BLOB + BLOB_MAX + len(pool) + 0xFFFF) & ~0xFFFF
        HEAP_END = NP.NbuProbe.RAM + 0xF00000
        STACK = NP.NbuProbe.RAM + RAM_SIZE - 0x100

    probe = QsProbe(img[:NP.SEG0_SIZE])
    pool_at = probe.BLOB + probe.BLOB_MAX
    P.check(pool_at + len(pool) <= probe.HEAP, "pool does not fit below the probe heap")
    probe.install_arena()
    probe.allow(*probe.OBJECT_FACTORY, "stock object factory")
    for address in U._native_stock_services():
        probe.stub(address, "stock UI construction service")
    probe.write(pool_at, bytes(pool))
    probe.open(blob=page, magic=False, cursor=0, pool=(len(pool), pool_at), owner=True)
    for record in N.split(page):
        trace = probe.record()
        P.check((trace.token, trace.cursor_in, trace.consumed) == (record.tag, record.offset, record.size)
                and not probe.error_flag(), f"native parser disagrees at record {trace.index}")
    P.check(probe.traces[-1].result == 1 and not probe.survey and not probe.discovered,
            "native parse did not terminate under the fixed allow-list")
    return probe
