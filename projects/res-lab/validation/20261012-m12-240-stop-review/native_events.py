"""Native recorder diagnostics using the already reviewed logger ring ABI.

No ARM code or hooks are installed. Native log expand owns its own MEM0
allocation. Save old rings before replacing them and restore the exact logger
configuration. DEBUG perturbs scheduling and is used only for diagnosis.
"""
import hashlib
import json
import struct

from inspect_current import C

LOGGER = 0xC303448C
CATEGORIES = ((2, 'RECMGR'), (23, 'RECMGR2'))
CAPACITY = 4096


def words(at, n=1):
    result = C.live.putfile.mem_get(at, n, tries=1)
    assert len(result) == n and all(w is not None for w in result)
    return result


def header(bit):
    ptr = words(LOGGER + 0x20 + 4 * bit)[0]
    assert 0xC3000000 <= ptr < 0xC4000000 or 0x45000000 <= ptr < 0x60000000
    desc = words(ptr, 8)
    base, count, cursor = desc[:3]
    assert desc[4:6] == [1 << bit, 0]
    assert base <= cursor < base + count * 28 and (cursor - base) % 28 == 0
    static = desc[7] == 0xC0727508 and desc[6] == 0 and count == 256
    dynamic = desc[7] == 0xC0727374 and desc[6] == 1 and count == CAPACITY
    assert static or dynamic, (hex(ptr), desc)
    assert static and 0xC3000000 <= base < base + count * 28 <= 0xC4000000 or \
        dynamic and 0xC5000000 <= base < base + count * 28 <= 0xC6000000
    return ptr, desc


def export(dest):
    dest.mkdir()
    assert words(LOGGER, 2) == [0, 0]
    report = {}
    for bit, name in CATEGORIES:
        ptr, desc = header(bit)
        data = bytearray()
        n = desc[1] * 7
        for offset in range(0, n, 64):
            part = words(desc[0] + 4 * offset, min(64, n - offset))
            data.extend(struct.pack('<%dI' % len(part), *part))
        assert header(bit) == (ptr, desc)
        (dest / (name + '.bin')).write_bytes(data)
        rows = [struct.unpack_from('<7I', data, i * 28) for i in range(desc[1])]
        index = (desc[2] - desc[0]) // 28
        rows = rows[index:] + rows[:index] if desc[3] else rows[:index]
        events = [{'code': hex(w[0]), 'timestamp': w[1], 'thread': w[2] & 255,
                   'level': (w[2] >> 8) & 255, 'format': w[2] >> 16,
                   'values': list(w[3:])} for w in rows]
        (dest / (name + '.json')).write_text(json.dumps(events, indent=2) + '\n')
        report[name] = {'descriptor_address': hex(ptr), 'descriptor': desc,
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'events': len(events), 'overwrites': desc[3]}
    (dest / 'rings.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


class Session:
    def __init__(self, dest):
        self.dest = dest
        self.before = None
        self.mutated = False
        self.restored = False

    def prepare(self):
        C.idle()
        self.before = words(LOGGER, 8)
        assert self.before[:4] == [0xFFFFFFFF, 0xFFFFFFFF, 0, 2]
        for bit, _ in CATEGORIES:
            assert header(bit)[1][1] == 256
        (self.dest / 'logger-before.json').write_text(json.dumps(self.before) + '\n')
        self.mutated = True
        C.live.checked_sh('log inact ALL')
        export(self.dest / 'logs-before')
        for bit, name in CATEGORIES:
            C.live.checked_sh('log expand ' + name + ' ' + str(CAPACITY))
            assert header(bit)[1][1:4] == [CAPACITY, header(bit)[1][0], 0]
        C.live.checked_sh('log level DEBUG')
        C.live.checked_sh('log act RECMGR RECMGR2')
        assert words(LOGGER, 4) == [0x800004, 0, 0, 0]

    def finish(self):
        C.idle()
        assert words(LOGGER, 4) == [0x800004, 0, 0, 0]
        C.live.checked_sh('log inact ALL')
        export(self.dest / 'logs-after')
        self.restore()

    def restore(self):
        if self.restored or not self.mutated:
            return
        C.idle()
        C.live.checked_sh('log inact ALL')
        for bit, name in CATEGORIES:
            if header(bit)[1][1] == CAPACITY:
                C.live.checked_sh('log expand ' + name)
            assert header(bit)[1][1] == 256
        C.live.checked_sh('log level WARNING')
        C.live.checked_sh('log act ALL')
        restored = words(LOGGER, 8)
        assert restored == self.before
        (self.dest / 'logger-restored.json').write_text(json.dumps(restored) + '\n')
        self.restored = True
