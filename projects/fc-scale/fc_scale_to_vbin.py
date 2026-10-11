#!/usr/bin/env python3
"""Turn an AutoRun-only card into an fpSup payload container.

sigma-fp-lab's False Color / EL Zone card is 728 `mem set` lines and nothing
else: no VSHL.BIN, no loader, the code spelled out word by word.  fpSup-Merge
merges payload *containers* -- "VBIN", a count, an entry, one (dest, len) per
section -- so the card cannot be ticked alongside the gyro logger or the USB
shell as it stands.  This reads the AutoRun and writes the container.

What it does NOT do is translate.  Every payload byte in the output is the byte
the AutoRun wrote, at the address the AutoRun wrote it to, and the run verifies
that by replaying the container the way stage2 places it and comparing the
result against the AutoRun's own final memory image, word for word.  Two things
are deliberately different, and both are printed:

  * the `echo`-handler borrow (0xC0BAC2F8) does not travel.  It was the card's
    way of getting a cache publish between two groups of writes; a VBIN card
    gets that from the loader, which publishes before it calls the entry.

  * the three firmware hook words are not sections.  Sections are placed in
    table order with one publish at the end of the pass, so a hook armed from
    the table can be armed before the code it branches to is visible -- and one
    of these three fires on every display submit.  They travel as a table in
    fc_scale_entry.S instead, which stage2 calls after publishing.

    usage:
      ./fc_scale_to_vbin.py CARD_DIR --out DIR

The card's own addresses are the window fpSup-Gyro's payload lives in, so a
gyro+FC card is refused -- correctly, and by name.  Moving it is a rebuild, not
a patch: fc_scale_rebuild.py beside this file does that from their source, which
takes the base as a constant and recomputes the hooks from the symbols.  (There
was a `--rebase` here that relocated the machine words instead.  It worked, and
it aimed at 0xC0735000, which their own build rejects because the stock image is
not zero there.  A conversion tool has no business choosing an address.)
"""
import argparse, hashlib, pathlib, re, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
COMPOSER = REPO / 'fpSup/tools/card-composer/index.html'
STUB_SRC = HERE / 'fc_scale_entry.S'

ENTRY_AT = 0xC072E064          # CAT.entry_at -- the payload window opens here
PARK_AT = 0xC072EFB4           # CAT.park_at  -- and closes here
PAD_TO = 0x8000                # CAT.pad_to
MAGIC = b'VBIN'
ECHO_SLOT = 0xC0BAC2F8         # the borrowed command handler: not carried
PRIVATE = (0xC0730000, 0xC0740000)   # og3k_load.py's private window


# --- reading the card ------------------------------------------------------

def read_autorun(path):
    """Every `mem set`, in file order.  Other commands are the script's own
    business (the banner, the OSD layer) and the fpSup templates do the same
    ones; anything unexpected is reported rather than ignored."""
    writes, others = [], []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        m = re.fullmatch(r'mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)', s)
        if m:
            writes.append((int(m.group(1), 16), int(m.group(2), 16)))
        else:
            others.append((n, s))
    return writes, others


def group(writes):
    """Contiguous ascending runs of one word each, in first-seen order."""
    runs = []
    for addr, val in writes:
        if runs and addr == runs[-1][0] + 4 * len(runs[-1][1]):
            runs[-1][1].append(val)
        else:
            runs.append([addr, [val]])
    return [(a, b''.join(struct.pack('<I', v) for v in w)) for a, w in runs]


def classify(runs):
    """Payload runs, hook words, and the handler borrow.

    A run of more than one word is payload -- it is code or a state block being
    spelled out.  A single word is a hook, and `main` then insists it really is
    a branch into one of the payload runs; a card whose single word is anything
    else is a card this conversion has not been thought through for, and it
    stops rather than guessing.  Which window the payload lands in is checked
    separately, because a rebuilt card names a different one on purpose."""
    payload, hooks, borrow = [], [], []
    for addr, blob in runs:
        if addr == ECHO_SLOT:
            borrow.append((addr, struct.unpack('<I', blob)[0]))
        elif len(blob) > 4:
            payload.append((addr, blob))
        else:
            hooks.append((addr, struct.unpack('<I', blob)[0]))
    return payload, hooks, borrow


def window_of(lo, hi):
    """Which window the payload occupies, and how much room is left above it
    for the entry.  The cave's payload window is bounded by the park stub; the
    private window is the one og3k lives in and og3k_load.py measured."""
    if ENTRY_AT <= lo and hi <= PARK_AT:
        return 'the cave payload window', PARK_AT
    if PRIVATE[0] <= lo and hi <= PRIVATE[1]:
        return 'the private window og3k uses', PRIVATE[1]
    return None, None


def branch_target(site, word):
    """The address an ARM `b` at `site` encoded as `word` goes to, or None."""
    if word >> 24 != 0xEA:
        return None
    off = word & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return (site + 8 + (off << 2)) & 0xFFFFFFFF


def encode_branch(site, target):
    off = (target - site - 8) >> 2
    return 0xEA000000 | (off & 0xFFFFFF)


# --- the container ---------------------------------------------------------

def catalogue_stage2():
    """The current loader helper, out of the composer page.  A card that is
    merged has its first section dropped and replaced with this one anyway; a
    card used on its own needs it, because loader.S branches to the end of the
    table and whatever is first IS the helper."""
    import base64, json
    html = COMPOSER.read_text()
    cat = json.loads(re.search(r'<script id="cat"[^>]*>([\s\S]*?)</script>',
                               html).group(1))
    return base64.b64decode(cat['stage2']['b'])


def assemble_stub(hooks):
    sys.path.insert(0, str(REPO / 'fpSup/fp_usb_shell'))
    import armasm
    code = bytearray(armasm.assemble(STUB_SRC))
    for site, word in hooks:
        code += struct.pack('<II', site, word)
    code += struct.pack('<I', 0)
    return bytes(code)


def container(sections, entry):
    body = b''
    table = b''
    for dest, blob in sections:
        table += struct.pack('<II', dest, len(blob))
        body += blob + b'\0' * (-len(blob) % 4)
    out = MAGIC + struct.pack('<III', len(sections), entry, len(body)) \
        + table + body
    if len(out) > PAD_TO:
        sys.exit(f'container is {len(out)} bytes, past {PAD_TO}')
    return out + b'\0' * (PAD_TO - len(out))


# --- the check that matters ------------------------------------------------

def replay(blob, hook_table_from_stub):
    """Place the container the way stage2 does -- pass one, firmware
    destinations, in table order -- then run what the entry's table says.
    Returns the memory image as {address: word}."""
    assert blob[:4] == MAGIC
    count, entry, _len = struct.unpack_from('<III', blob, 4)
    mem, off = {}, 16 + 8 * count
    for i in range(count):
        dest, ln = struct.unpack_from('<II', blob, 16 + 8 * i)
        if dest:
            for j in range(0, ln, 4):
                mem[dest + j] = struct.unpack_from('<I', blob, off + j)[0]
        off += ln + (-ln % 4)
    for site, word in hook_table_from_stub:
        mem[site] = word
    return mem, entry


def intended(writes):
    """What the AutoRun leaves behind, last write wins, minus the borrow."""
    mem = {}
    for addr, val in writes:
        if addr == ECHO_SLOT:
            continue
        mem[addr] = val
    return mem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('card', type=pathlib.Path,
                    help='the card directory, or its AutoRun.txt')
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--name', default='fpSup.BIN')
    a = ap.parse_args()

    src = a.card if a.card.is_file() else a.card / 'AutoRun.txt'
    writes, others = read_autorun(src)
    payload, hooks, borrow = classify(group(writes))

    print(f'{src}')
    print(f'  {len(writes)} mem set, {len(others)} other commands')
    for n, s in others:
        print(f'      line {n}: {s}')
    print(f'  {len(borrow)} write(s) to the echo handler slot '
          f'0x{ECHO_SLOT:08X} -- not carried, the loader publishes instead')

    lo = min(a_ for a_, _ in payload)
    hi = max(a_ + len(b) for a_, b in payload)
    for addr, blob in payload:
        print(f'  payload  0x{addr:08X}..0x{addr + len(blob):08X}  '
              f'{len(blob):5d} B')
    for site, word in hooks:
        t = branch_target(site, word)
        if t is None or not (lo <= t < hi):
            sys.exit(f'0x{site:08X}: 0x{word:08X} is not a branch into the '
                     f'payload -- not converted')
        print(f'  hook     0x{site:08X} -> 0x{t:08X}  (b, via the entry table)')

    stub_at = (hi + 0x3F) & ~0x3F

    stub = assemble_stub(hooks)
    where, top = window_of(min(x for x, _ in payload),
                           max(x + len(b) for x, b in payload))
    if where is None:
        sys.exit(f'the payload is in no window this knows about: '
                 f'0x{min(x for x, _ in payload):08X}..'
                 f'0x{max(x + len(b) for x, b in payload):08X}')
    print(f'  window   {where}, up to 0x{top:08X}')
    if stub_at + len(stub) > top:
        sys.exit(f'the entry would run from 0x{stub_at:08X} past '
                 f'0x{top:08X}, the end of that window')
    print(f'  entry    0x{stub_at:08X}  {len(stub)} B  '
          f'({len(hooks)} hook words + terminator)')

    sections = [(0, catalogue_stage2())] + payload + [(stub_at, stub)]
    blob = container(sections, stub_at)

    # --- replay it and compare with the card ------------------------------
    got, entry = replay(blob, hooks)
    want = intended(writes)
    missing = {k: v for k, v in want.items() if got.get(k) != v}
    extra = {k: v for k, v in got.items()
             if k not in want and not (stub_at <= k < stub_at + len(stub))}
    if missing or extra:
        for k, v in sorted(missing.items())[:8]:
            print(f'  MISMATCH 0x{k:08X}: card 0x{v:08X}, '
                  f'container {got.get(k)}')
        for k, v in sorted(extra.items())[:8]:
            print(f'  EXTRA    0x{k:08X}: 0x{v:08X}')
        sys.exit('the container does not reproduce the card')
    print(f'  verified {len(want)} words: every byte the AutoRun wrote, '
          f'at the address it wrote it to')
    assert entry == stub_at

    a.out.mkdir(parents=True, exist_ok=True)
    dest = a.out / a.name
    dest.write_bytes(blob)
    print(f'  {dest}  {len(blob)} B  sha256 '
          f'{hashlib.sha256(blob).hexdigest()[:24]}')
    print('  drop it on fpSup-Merge (Show the technical detail -> the drop '
          'zone) and tick what else you want.')


if __name__ == '__main__':
    main()
