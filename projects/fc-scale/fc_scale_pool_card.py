#!/usr/bin/env python3
"""Build sigma-fp-lab's False Color / EL Zone payload as an fpSup container
that asks the allocator for its memory.

The card they publish, and fc_scale_to_vbin.py's conversion of it, want about
three kilobytes at a fixed cave address.  There is no such hole left: after the
loader, the payload window (the gyro logger's), the park stub, the shell's
state, the boot descriptor, the host's one-shot block and OG3K/OG2K, the stock
image's zero region has nothing contiguous that big.  So that card composes with
the gyro logger or with open gate, never both.

This build takes the other route, the one worker.S and the gyro profile
generator already take: the payload goes in memory the allocator hands out, and
the cave keeps only what has to have a fixed address --

    0xC072E080  state block, 144 B   their code names it, so it stays put
    0xC072E110  three trampolines    a firmware site can reach these; the pool
                                     is 48 MB away and `b` reaches 32
    0xC072E128  allocator descriptor 16 B, has to outlive the H_GET call
    0xC072E138  the pool address     published, so a host tool can find it

188 bytes, all of it inside 0xC072E064..0xC072E200 -- the head of the payload
window, which no shipped card uses: the gyro logger's first section is at
0xC072E200 and OG3K starts at 0xC0730700.  So this composes with everything.

Their source is not modified.  It does not need to be: the payload is position
independent apart from the state block (every branch inside it is relative, its
four address computations are pc-relative, and no literal word holds a cave
address), and the state block is exactly what stays in the cave.  What the
rebuild changes is one constant, STATE, which their builder already takes.

    ./fc_scale_pool_card.py --lab-repo DIR --out DIR

Needs, in DIR: their tools/ and src/, plus analysis/MAIN_c0000000.bin and
reference/fpSup/fp_usb_shell/ -- both can be symlinks into this tree.  See the
note beside this file.
"""
import argparse, hashlib, importlib.util, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
COMPOSER = REPO / 'fpSup/tools/card-composer/index.html'
ENTRY_SRC = HERE / 'fc_pool_entry.S'

ENTRY_AT = 0xC072E064          # CAT.entry_at: the payload window opens here
FIRST_USED = 0xC072E200        # ...and the gyro logger's first section
PAD_TO = 0x8000

# The anchors, in the 412 bytes at the head of the payload window.
STATE_AT = 0xC072E080
TRAMP_AT = 0xC072E110
DESC_AT = 0xC072E128
POOLPTR_AT = 0xC072E138
STATE_SIZE = 0x90              # their STATE_SIZE
DESC_SIZE = 0x10               # the allocator descriptor, as loader.S sizes it
TRAMP = 0xE51FF004             # ldr pc, [pc, #-4] -- the next word is the target


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def catalogue_stage2():
    import base64, json, re
    cat = json.loads(re.search(r'<script id="cat"[^>]*>([\s\S]*?)</script>',
                               COMPOSER.read_text()).group(1))
    return base64.b64decode(cat['stage2']['b'])


def branch(site, target):
    off = target - site - 8
    if off % 4 or not -0x2000000 <= off < 0x2000000:
        sys.exit(f'0x{site:08X} -> 0x{target:08X} is out of branch range')
    return 0xEA000000 | ((off >> 2) & 0xFFFFFF)


def movw_movt_values(blob):
    """Every absolute address the blob builds with a movw/movt pair."""
    out, pending = [], {}
    for i in range(0, len(blob) - 3, 4):
        w = struct.unpack_from('<I', blob, i)[0]
        rd, imm = (w >> 12) & 0xF, ((w >> 4) & 0xF000) | (w & 0xFFF)
        if (w & 0x0FF00000) == 0x03000000:
            pending[rd] = imm
        elif (w & 0x0FF00000) == 0x03400000 and rd in pending:
            out.append((imm << 16) | pending.pop(rd))
    return out


def build(lab_repo: pathlib.Path):
    """Returns (container bytes, a dict of everything worth printing)."""
    lab = load(lab_repo / 'tools/build_fcscale_autorun.py', 'build_fcscale_autorun')
    sys.path[:0] = [str(lab_repo / 'reference/fpSup/fp_usb_shell')]
    from armasm import assemble, symbols

    image = lab.MAIN.read_bytes()
    if hashlib.sha256(image).hexdigest() != lab.MAIN_SHA:
        sys.exit('their build requires the verified Ver.5.02 MAIN image')
    # Their own site checks, kept: a payload armed onto a site that is not the
    # one it replays is a freeze, and this is the only place it can be caught.
    for site, want, why in ((lab.PRESS_SITE, lab.SITE_STOCK, 'press'),
                            (lab.RELEASE_SITE, lab.SITE_STOCK, 'release'),
                            (lab.SUBMIT_SITE, lab.SUBMIT_STOCK, 'submit')):
        got = lab.word(image, site)
        if got != want:
            sys.exit(f'the {why} site 0x{site:08X} holds 0x{got:08X}, '
                     f'not 0x{want:08X}')

    # The anchors: inside the window's head, in order, not overlapping, and
    # zero in the stock image -- the same check their build runs on its cave.
    anchors = [('state', STATE_AT, STATE_SIZE), ('trampolines', TRAMP_AT, 24),
               ('descriptor', DESC_AT, DESC_SIZE), ('pool pointer', POOLPTR_AT, 4)]
    at = ENTRY_AT
    for why, addr, size in anchors:
        if addr < at:
            sys.exit(f'the {why} anchor at 0x{addr:08X} is below 0x{at:08X}')
        at = addr + size
    if at > FIRST_USED:
        sys.exit(f'the anchors reach 0x{at:08X}, past 0x{FIRST_USED:08X} where '
                 f'the gyro logger starts')
    for why, addr, size in anchors:
        for a in range(addr, addr + size, 4):
            if lab.word(image, a):
                sys.exit(f'the {why} anchor at 0x{a:08X} is not zero in stock')

    # Their payload, unmodified, with the state block where we put it.
    lab.STATE = STATE_AT
    lab.NATIVE_INC.write_text(lab.native_include(image))
    code = assemble(lab.ROOT / 'src/fcscale.S', lab.defines())
    marks = symbols(lab.ROOT / 'src/fcscale.S', lab.defines())
    code += b'\0' * (-len(code) % 4)
    named = set(movw_movt_values(code))
    if STATE_AT not in named:
        sys.exit('the payload does not name the state block: the STATE define '
                 'did not reach the assembly')
    stray = [v for v in named if ENTRY_AT <= v < FIRST_USED and v != STATE_AT]
    if stray:
        sys.exit(f'the payload names 0x{stray[0]:08X} in the cave as well as '
                 f'its state block -- not just position independent code')
    hooks = [('press', lab.PRESS_SITE, marks['fc_press']),
             ('release', lab.RELEASE_SITE, marks['fc_release']),
             ('submit', lab.SUBMIT_SITE, marks['fc_submit'])]
    for why, _site, off in hooks:
        if not 0 <= off < len(code):
            sys.exit(f'{why} is at +0x{off:X}, outside the payload')

    # The entry, and the table it reads.
    entry_code = assemble(ENTRY_SRC)
    entry_code += b'\0' * (-len(entry_code) % 4)
    size = (len(code) + 0xFF) & ~0xFF
    lists = b''
    for n, (_why, _site, off) in enumerate(hooks):          # pool-relative
        lists += struct.pack('<II', TRAMP_AT + 8 * n + 4, off)
    lists += struct.pack('<I', 0)
    for n, (_why, site, _off) in enumerate(hooks):          # absolute, last
        lists += struct.pack('<II', site, branch(site, TRAMP_AT + 8 * n))
    lists += struct.pack('<I', 0)
    header = struct.pack('<IIIII', DESC_AT, size, POOLPTR_AT,
                         0x14 + len(lists), len(code))
    assert len(header) == 0x14
    blob = entry_code + header + lists + code

    tramp = b''.join(struct.pack('<II', TRAMP, 0) for _ in hooks)
    sections = [(0, catalogue_stage2()),
                (STATE_AT, b'\0' * STATE_SIZE),
                (TRAMP_AT, tramp),
                (DESC_AT, b'\0' * DESC_SIZE),
                (POOLPTR_AT, b'\0' * 4),
                (0, blob)]

    body, table = b'', b''
    offsets = []
    off = 16 + 8 * len(sections)
    for dest, s in sections:
        offsets.append(off)
        table += struct.pack('<II', dest, len(s))
        body += s + b'\0' * (-len(s) % 4)
        off += len(s) + (-len(s) % 4)
    entry = offsets[-1]                    # the entry section runs where it lands
    out = b'VBIN' + struct.pack('<III', len(sections), entry, len(body)) \
        + table + body
    if len(out) > PAD_TO:
        sys.exit(f'{len(out)} bytes, past {PAD_TO}')
    out += b'\0' * (PAD_TO - len(out))

    return out, dict(code=code, entry_code=entry_code, blob=blob, hooks=hooks,
                     size=size, entry=entry, sections=sections, lab=lab,
                     anchors=anchors, marks=marks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lab-repo', type=pathlib.Path, required=True)
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--name', default='fpSup.BIN')
    a = ap.parse_args()

    out, info = build(a.lab_repo)
    print(f'payload   {len(info["code"])} B, into 0x{info["size"]:X} B from the '
          f'allocator (class 0, USER)')
    print(f'entry     {len(info["entry_code"])} B of code + '
          f'{len(info["blob"]) - len(info["entry_code"]) - len(info["code"])} B '
          f'of table, at file offset 0x{info["entry"]:X}')
    for why, addr, size in info['anchors']:
        print(f'anchor    0x{addr:08X}  {size:4d} B  {why}')
    for n, (why, site, off) in enumerate(info['hooks']):
        print(f'hook      0x{site:08X} -> trampoline 0x{TRAMP_AT + 8 * n:08X} '
              f'-> pool+0x{off:X}  ({why})')
    cave = sum(size for _why, _a, size in info['anchors'])
    print(f'cave      {cave} B in total, 0x{STATE_AT:08X}..'
          f'0x{POOLPTR_AT + 4:08X}, inside the window head '
          f'0x{ENTRY_AT:08X}..0x{FIRST_USED:08X}')

    a.out.mkdir(parents=True, exist_ok=True)
    dest = a.out / a.name
    dest.write_bytes(out)
    print(f'{dest}  {len(out)} B  sha256 {hashlib.sha256(out).hexdigest()[:24]}')


if __name__ == '__main__':
    main()
