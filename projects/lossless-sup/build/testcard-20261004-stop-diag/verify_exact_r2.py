import hashlib
import json
import pathlib
import re
import struct
import subprocess
import sys

ROOT = pathlib.Path('/Users/dido/Developer.localized/SIGMAfp_re')
sys.path.insert(0, str(ROOT / 'fpSup/lossless'))
import test_card_emulation as M
T = M.T


def need(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ExactCamera(M.CardCamera):
    def __init__(self, *a, **kw):
        self.chain_targets = {}
        self.chain_calls = []
        super().__init__(*a, **kw)

    def _hook(self, mu, address, size, user):
        if address in self.chain_targets:
            name = self.chain_targets[address]
            need(self.r(M.UC_ARM_REG_SP) % 8 == 0, 'entry chain SP alignment')
            need(self.r(M.UC_ARM_REG_R0) == address, 'entry does not receive itself')
            self.chain_calls.append(name)
            if name != 'lossless':
                return self._ret(0)  # explicit shell/OG entry stubs, not their validation
        return super()._hook(mu, address, size, user)


class ExactCase(M.CardEmulationTests):
    def boot(self, mutate_site=None):
        need(mutate_site is None, 'this exact-byte run does not mutate a site before boot')
        cam = ExactCamera(self.loader, self.bin)
        cam.now = 15_000_000
        # The actual plain/debug AutoRun uses the echo entry, not fast +4.
        # Fast is also first tested through its real cold/echo entry.
        incoming = T.STACK - 0x1004
        _, returned = cam.call(T.CAVE_LOW, sp=incoming)
        self.assertEqual(returned, incoming)
        self.assertEqual(cam.calls.count('ENTRY'), 1)
        self.assertEqual([force for _, force in cam.registered], [0, 1])
        self.assertEqual(len({obj for obj, _ in cam.registered}), 1)
        cam.staging = cam.entry - self.header_entry
        cam.launcher = cam.staging + self.launcher_offset
        self.assertEqual(bytes(cam.mu.mem_read(cam.launcher, len(self.blob))), self.blob)
        for site, stock in M.SITES.values():
            self.assertEqual(cam.word(site), stock)
        return cam


def verify(directory):
    directory = pathlib.Path(directory)
    print('verify ' + directory.name, file=sys.stderr, flush=True)
    facts = json.loads((directory / 'build.json').read_text())
    blob_facts = facts['blob']
    need(facts['opengate'] == 'og3k', 'wrong OG configuration')
    need(not facts['written_to_card'] and not facts['camera_tested'], 'artifact status changed')
    for name, wanted in facts['outputs'].items():
        need(sha((directory / name).read_bytes()) == wanted, 'artifact hash mismatch: ' + name)
    # card_symbols() assembles the CURRENT source only to extract offsets.
    # Its source must match this build; executable payload is always the file.
    for path in ('fpSup/lossless/native/card.S', 'fpSup/lossless/build_card.py'):
        need(sha((ROOT / path).read_bytes()) == facts['sources'][path], 'source drift: ' + path)
    M.LAYOUT = json.loads((directory / 'layout.json').read_text())['fields']
    need(M.LAYOUT == blob_facts['layout'], 'layout does not match artifact')
    M.CARD_BLOCK = blob_facts['block_bytes']
    M.C_ENTRIES = {name: M.BLOCK + blob_facts['c_base'] + (offset & ~1)
                   for name, offset in blob_facts['entries'].items()}
    case = ExactCase()
    case.bin = (directory / 'fpSup.BIN').read_bytes()
    case.blob = (directory / 'lossless.bin').read_bytes()
    text = (directory / 'AutoRun.txt').read_text()
    sets = [(int(a, 16), int(v, 16)) for a, v in re.findall(
        r'^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)', text, re.M)]
    case.loader = {a: v for a, v in sets if T.CAVE_LOW <= a < T.CAVE_LOW + 0x200}
    need(case.loader and T.CAVE_LOW in case.loader, 'AutoRun loader not found')
    magic, count, case.header_entry, data_bytes = struct.unpack_from('<4sIII', case.bin)
    need(magic == b'VBIN', 'not VBIN')
    sections, offset = [], 16 + 8 * count
    for i in range(count):
        dest, length = struct.unpack_from('<II', case.bin, 16 + 8 * i)
        need(offset + length <= len(case.bin), 'section outside artifact')
        sections.append((dest, length, offset))
        offset += length + (-length % 4)
    need(offset <= int(facts['loader_read'], 16), 'VBIN exceeds recorded read cap')
    matches = [off for dst, length, off in sections
               if dst == 0 and case.bin[off:off+length] == case.blob]
    need(len(matches) == 1, 'exact launcher missing/ambiguous')
    case.launcher_offset = matches[0]
    entry_sec = [(dst, length, off) for dst, length, off in sections
                 if off <= case.header_entry < off + length]
    need(len(entry_sec) == 1 and entry_sec[0][0] == 0, 'entry chain not a zero-destination section')
    _, length, entry_off = entry_sec[0]
    tables = [at for at in range(case.header_entry, entry_off + length, 4)
              if struct.unpack_from('<I', case.bin, at)[0] == at]
    need(len(tables) == 1, 'entry table self-offset missing/ambiguous')
    entries, at = [], tables[0] + 4
    while at < entry_off + length:
        value, = struct.unpack_from('<I', case.bin, at)
        at += 4
        if value == 0:
            break
        entries.append(value)
    need(value == 0, 'entry table not terminated')
    labels = [('lossless' if e == case.launcher_offset else
               'opengate' if e >= 0x40000000 else 'usb-shell') for e in entries]
    want = (['usb-shell'] if facts['usb_shell'] else []) + ['lossless', 'opengate']
    need(labels == want, 'wrong entry order: ' + repr(labels))
    for address, expected in M.SITES.values():
        declarations = [(size, case.bin[off:off+size]) for dst, size, off in sections if dst == address]
        need(declarations == [(4, struct.pack('<I', expected))], 'missing exact stock hook section')
    print('boot exact echo loader', file=sys.stderr, flush=True)
    cam = case.boot()
    print('boot done; journal + entry chain', file=sys.stderr, flush=True)
    obj = cam.registered[0][0]
    cursor, journal = cam.word(obj + 8), {}
    for _ in range(count + 8):
        address = cam.word(cursor)
        if not address:
            break
        size = cam.word(cursor + 4)
        need(size <= len(case.bin), 'journal span unreasonable')
        journal[address] = bytes(cam.mu.mem_read(cursor + 8, size))
        cursor += 8 + size
    else:
        raise AssertionError('journal lacks bounded terminator')
    for address, expected in M.SITES.values():
        need(journal.get(address) == struct.pack('<I', expected), 'hook original missing from journal')
    # Execute the exact entry dispatcher. Shell/OG are deliberately stubbed;
    # the Lossless launcher itself copies and initializes from the real BIN.
    entry = cam.entry
    cam.entry = None
    cam.chain_targets = {(cam.staging + e if e < 0x40000000 else e): name
                         for e, name in zip(entries, labels)}
    cam.launching = True
    _, returned = cam.call(entry, r0=entry, sp=T.STACK - 0x1000)
    cam.launching = False
    need(returned == T.STACK - 0x1000 and cam.chain_calls == labels, 'entry chain execution/ABI')
    symbols = M.card_symbols()
    lo, hi = symbols['g_card'], symbols['stop_resume']
    resident = bytes(cam.mu.mem_read(M.BLOCK, len(case.blob)))
    need(resident[:lo] == case.blob[:lo] and resident[hi:] == case.blob[hi:], 'resident copy differs')
    need(all(struct.unpack('<%dI' % ((hi-lo)//4), resident[lo:hi])), 'unresolved resident entries')
    installed = {}
    for name, (site, original) in M.SITES.items():
        instruction = cam.word(site)
        need(instruction != original, 'hook not installed: ' + name)
        displacement = instruction & 0xFFFFFF
        if displacement & 0x800000:
            displacement -= 0x1000000
        veneer = site + 8 + 4 * displacement
        need(cam.word(veneer) == 0xE51FF004, 'not an absolute veneer')
        need(M.BLOCK <= cam.word(veneer + 4) < M.BLOCK + len(case.blob), 'shim outside resident blob')
        installed[name] = hex(instruction)
    for _ in range(2):
        cam.call(cam.word(obj + 4), r0=obj, r1=4)
    for site, original in M.SITES.values():
        need(cam.word(site) == original, 'power-off did not restore hook')
    print('entry chain and restore done', file=sys.stderr, flush=True)
    tests = [name for name in dir(M.CardEmulationTests) if name.startswith('test_')]
    # All existing launcher/shim assertions, now fed exact files and this
    # plain-capable boot method, never setUpClass()/build_card().
    tests = [name for name in tests if name not in (
        'test_a_site_that_is_not_stock_arms_nothing',)]
    # Shared exact payload: skip repeated helpers for the fast package.
    if directory.name == 'fast-og3k-r2':
        tests = []
    for name in tests:
        print(name, file=sys.stderr, flush=True)
        getattr(case, name)()
    for name, wanted in facts['outputs'].items():
        need(sha((directory / name).read_bytes()) == wanted, 'artifact changed during verification')
    return {'directory': str(directory), 'status': 'PASS', 'tests': tests,
            'hashes': facts['outputs'], 'section_count': count, 'entry_order': labels,
            'entry_addresses_or_offsets': [hex(e) for e in entries],
            'journaled_lossless_sites': len(M.SITES), 'installed': installed,
            'poweroff_restore_invocations': 2, 'all_lossless_sites_restored': True,
            'exact_launcher_sha256': sha(case.blob),
            'loader_from_actual_autorun': True,
            'firmware_main_sha256': sha(T.IMAGE.read_bytes()),
            'limits': ['USB shell and OpenGate entry bodies were stubbed; their order/ABI was executed.',
                       'No codec, real scheduler, storage, hardware or UI lifetime validation.',
                       'No comparison to released AutoRun compatibility; local shared loader includes FS3 changes.',
                       'Loader cold/echo path tested; retained-image/settings fast paths not covered here.']}


if __name__ == '__main__':
    if sys.argv[1:2] == ['--one']:
        print(json.dumps(verify(sys.argv[2]), indent=2))
    else:
        results = []
        for directory in sys.argv[1:]:
            try:
                run = subprocess.run([sys.executable, '-B', __file__, '--one', directory],
                                     capture_output=True, text=True, timeout=150)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError('bounded child timeout: ' + repr(error.stderr)) from error
            need(run.returncode == 0, 'child failed: %s\n%s\n%s' %
                 (run.returncode, run.stdout, run.stderr))
            results.append(json.loads(run.stdout))
            print('PASS ' + pathlib.Path(directory).name, file=sys.stderr, flush=True)
        print(json.dumps({'artifacts': results}, indent=2))
