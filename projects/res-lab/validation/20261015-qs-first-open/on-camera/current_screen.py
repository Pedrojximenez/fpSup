"""Observe one active screen with the verified bounded camera-side snapshot.
Caller owns the AF lease. Native keys are never replayed by this helper.
"""
import struct
import experiment as E

class Screen:
    def __init__(self):
        self.code = E.cave.claim('qs.firstopen.screen', 320)
        self.parm = E.pf.P
        blob = E.assemble(E.HERE / 'screen_snapshot.S', [f'P={self.parm}'])
        assert len(blob) <= 320
        E.pf.put(self.code, blob, 'screen')
        E.publish_rom_caches()

    def read(self):
        assert E.pf.mem_get(E.pf.ECHO_SLOT, tries=1) == [E.pf.ECHO_ORIG]
        try:
            E.pf.set_echo_handler(self.code)
            E.live.checked_sh('echo', timeout_ms=2000)
            words = E.pf.mem_get(self.parm + 0x40, 12, tries=1)
            assert len(words) == 12 and None not in words and words[3] == 1
            name = struct.pack('<8I', *words[4:]).split(b'\0')[0].decode('ascii')
            assert name and len(name) < 32
            return name
        finally:
            assert E.pf.mem_get(E.pf.ECHO_SLOT, tries=1)[0] in (E.pf.ECHO_ORIG, self.code)
            E.pf.set_echo_handler(E.pf.ECHO_ORIG)
