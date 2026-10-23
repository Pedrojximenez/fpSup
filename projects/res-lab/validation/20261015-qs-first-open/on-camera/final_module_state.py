"""Read the identified resident SupManager and RES-Custom after a visual trial."""
import argparse, fcntl, json, struct
from pathlib import Path
import experiment as E

p = argparse.ArgumentParser()
p.add_argument('--variant', choices=('combined-fix8', 'combined-fix9', 'combined-fix10', 'combined-fix11', 'combined-fix12'), required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
assert not a.out.exists()

with open('/tmp/fp-af-fusion.lock', 'r') as lease:
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    daemon = E.daemon()
    idle = E.B.idle()
    state, identity = E.core_state(a.variant)
    site = 0xC056461C
    word = E.pf.mem_get(site, tries=1)[0]
    assert word & 0xFF000000 == 0xEB000000, hex(word)
    displacement = word & 0xFFFFFF
    if displacement & 0x800000:
        displacement -= 0x1000000
    veneer = site + 8 + 4 * displacement
    assert E.cave.CAVE_ARENA <= veneer < E.cave.CAVE_ARENA_END
    stub = E.pf.mem_get(veneer, 2, tries=1)
    assert stub[0] == 0xE51FF004
    target = stub[1]
    assert 0x45000000 <= target < 0x48000000 and target % 4 == 0
    loader = (E.HERE / 'run3/enabled-LOADER.BIN').read_bytes()
    needle = struct.pack('<4I', 0xE3510000, 0x0A000007, 0xE5D1C000, 0xE35C0046)
    assert loader.count(needle) == 1
    offset = loader.index(needle)
    code = E.pf.mem_get(target, 14, tries=1)
    assert struct.pack('<12I', *code[:12]) == loader[offset:offset + 48]
    ctx = code[13]
    assert 0x45000000 <= ctx < 0x48000000 and ctx % 4 == 0
    head = E.pf.mem_get(ctx, 64, tries=1)
    raw = struct.pack('<64I', *head)
    manager = (E.HERE / 'run3/backup/fpSup__UI__ALLSUPS.BIN').read_bytes()
    assert raw[:44] == manager[:44] and head[0] == 0x5A365446
    rows_at, count = ctx + head[30], head[49]
    assert 0 < count <= 32 and ctx <= rows_at < rows_at + 272 * count <= 0x48000000
    rows = E.pf.read_bulk(rows_at, 272 * count, 'SupManager rows')
    modules = []
    for i in range(count):
        row = rows[272 * i:272 * (i + 1)]
        name = row[:24].split(b'\0', 1)[0].decode('ascii')
        boot, enabled, error = struct.unpack_from('<3I', row, 52)
        modules.append(dict(file=name, boot=boot, enabled_next_boot=enabled, write_error=error))
    expected = ['00SHELL', '05STOPFX', '10LOSS', '20RECW', '30FCAP', '32RESCUS',
                '40FLIP', '40GYR2', '41DSQZ', '42TAPZ', '45RAWV']
    assert [m['file'] for m in modules] == expected
    assert all((m['boot'], m['enabled_next_boot'], m['write_error']) == (0, 1, 0) for m in modules)
    assert head[42] == 0
    flags = {k: E.pf.mem_get(state + E.L.S[k], tries=1)[0] for k in ('VR_UI', 'VR_WHY')}
    assert flags == {'VR_UI': 1, 'VR_WHY': 1}
    echo = E.pf.mem_get(E.pf.ECHO_SLOT, tries=1) == [E.pf.ECHO_ORIG]
    gui = E.pf.mem_get(0xC37B71E0, tries=1)[0]
    assert echo and gui == 0
    result = dict(variant=a.variant, identity=identity, daemon=daemon,
                  idle=E.B.idle(), **flags, manager_status=head[42], modules=modules,
                  echo_restored=echo, GUI_attributes=gui)
    a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
