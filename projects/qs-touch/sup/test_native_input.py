"""Native integer relay regression. Offline; no USB imports or camera access.

The actual SUP resource supplies the action fields. Original registration,
silent/notifying setters and controlAppVariable instructions execute. Page
event scheduling is explicit; allocator, Lua, mutex and callback are substitutes.
"""
from pathlib import Path
import struct
import sys
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'research/ui/tools/native_control_probe'))
import test_native_permission_binding as N
import page as P


@lru_cache(maxsize=2)
def private_page(blob):
    ui_off = struct.unpack_from('<I', blob, 56)[0]
    ui = blob[ui_off:]
    h = struct.unpack_from('<17I', ui)
    pack = ui[h[1]:h[1]+h[2]]
    page_at, = [off for name, off, _ in P.F.SL.native_rows(pack) if name == P.PAGE]
    refs = {}
    for k in range(h[5]):
        off, index = struct.unpack_from('<II', ui, h[6]+8*k)
        at = struct.unpack_from('<I', ui, h[3]+4*index)[0]
        refs[off] = ui[at:ui.index(b'\0', at)].decode()
    image = (ROOT/'out/MAIN_c0000000.bin').read_bytes()
    builder = P.Page(image)
    records = P.B.Q.N.split(pack, page_at)
    return records, refs, builder


@lru_cache(maxsize=2)
def relay(blob):
    records, refs, builder = private_page(blob)
    for k, rec in enumerate(records):
        raw = rec.to_bytes()
        if rec.tag != 0x10006 or builder.pool.text(P.B.u32(raw, 8)) != 'appVariableChangeEvent':
            continue
        fields = P.B.Q.fields(raw, builder.pool, builder.schemas)
        offset = fields['variable-name'][0]
        if refs.get(rec.offset+offset) != 'QST_Touch':
            continue
        assert P.B.u32(raw, 16) == 1
        assert P.B.u32(raw, fields['type'][0]) == 2
        action = records[k+1]
        ar = action.to_bytes()
        assert action.tag == 0x10009
        assert builder.pool.text(P.B.u32(ar, 8)) == 'controlAppVariable'
        af = P.B.Q.fields(ar, builder.pool, builder.schemas)
        return dict(event='QST_Touch',
                    destination=refs[action.offset+af['destination-variable'][0]],
                    source=refs[action.offset+af['source-variable'][0]],
                    source_type=P.B.u32(ar, af['source-type'][0]))
    raise AssertionError('SUP page has no native touch relay')


class InputProbe(N.PermissionProbe):
    CALLBACK = N.registry.RegistryProbe.SERVICES + 0x180
    EXTRA = ((0xC05F15E0, 0xC05F1EF8), (0xC05F1F58, 0xC05F1F5C),
             (0xC05D6BE0, 0xC05D6C68))

    def __init__(self, route):
        super().__init__(N.registry.load_firmware(ROOT/'out/seg0_c0000000.bin'))
        self.events = []
        self.route = route
        self.write_words(self.ROOT+0x130, self.ALLOCATOR, 0)
        self.names, self.descs = {}, {}
        for slot, name in enumerate(dict.fromkeys((route['source'], route['destination'])), 2):
            assert self.register(name=name, value=0, slot=slot) == 0
            at = self.NAME+slot*0x80
            assert self.run(N.registry.LOOKUP_APP, self.APP, at, self.OUT) == 0
            self.names[name], self.descs[name] = at, self.words(self.OUT)[0]
        pair = self.zero(8)
        self.write_words(pair, self.CALLBACK|1, 0)
        assert self.run(N.binding.SUBSCRIBE, self.APP, self.names[route['destination']], pair) == 0
        self.action, _, _, _ = self.component(0xC2E01440, 0xC2E01340,
            [self.names[route['destination']], route['source_type'], self.names[route['source']], 0, 0, 0, 0, 0])

    def _instruction(self, uc, address, size, data):
        if address == self.CALLBACK:
            desc = uc.reg_read(N.registry.REGS[0])
            self.events.append(self.words(desc+8)[0])
            self._return(0)
            return
        if address == 0xC0015808:
            pointer, count = (uc.reg_read(r) for r in N.registry.REGS[:2])
            assert count == 64
            self.write(pointer, bytes(4*count))
            self._return(pointer)
            return
        for start, end in self.EXTRA:
            if start <= address and address+size <= end:
                self.instructions += 1
                self.native_pcs.add(address)
                return
        super()._instruction(uc, address, size, data)

    def post_silent(self, value):
        self.write_words(self.ASSIGNMENT, 0, self.names[self.route['source']], value)
        assert self.run(N.binding.SET_SILENT, self.APP, 0, 1, self.ASSIGNMENT) == 0

    def run_action(self):
        assert self.run(0xC05F15E0, self.action, 0) == 0
