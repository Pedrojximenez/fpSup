"""One boot's timeline, all on the camera's own microsecond clock (power-on = 0).

Needs a card built with `build_v4.py --card --boot-markers` (implies --profile).
Run after the camera has booted and the USB shell answers; read-only:

    python3 -B projects/loader-v4/boot_timeline.py [--json out.json]

Sources (same clock: F_TICK_US 0xC002B6E0, which the firmware log also stamps):
  * marker array  0xC072E0B4: magic, count, stamps[14]  (build_autorun.py MARK_*)
      'MRKD' = this boot ran the AutoRun; 'NONE' = no AutoRun (Fast Start 2 warm boot);
      'MRK1' = the core never saw it (the loader did not run -- look at LOAD.LOG)
  * LOAD_START_US 0xC072F6F4  loader entered        (--profile)
  * LOAD_DONE_US  0xC072F6F8  loader finished
  * `log out INIT`, `log out UI`, `log out DISP`  firmware milestones (e.g. LvStarted)

Which stamps exist depends on the path the boot took:
  slow (no store hit): S0 S1 S2 S3 S4 S5 [loader] S6     (7 stamps)
  Fast Start 3 hit:    S0 S1 S2 S3 S4 [store -> loader] (5 stamps; the script stops)
  Fast Start 2 warm:   [loader]                          (0 stamps, magic NONE)
S1 - S0 is the cost of one marker (two lines: `mem set` + `echo`), measured every boot.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
from putfile import sh, mem_get  # noqa: E402

MARK_DATA, MARK_SLOTS = 0xC072E0B4, 14
LOAD_START_US, LOAD_DONE_US = 0xC072F6F4, 0xC072F6F8
MAGIC = {0x314B524D: 'MRK1', 0x444B524D: 'MRKD', 0x454E4F4E: 'NONE'}
LABELS = ['S0 AutoRun start (after the stamp routine is installed)',
          'S1 second stamp (S1-S0 = one marker)',
          'S2 before the first splash display',
          'S3 after the last splash display',
          'S4 before the store bootstrap (Fast Start 3)',
          'S5 before the spelled-out loader',
          'S6 after the spelled-out loader returns']
LOG = re.compile(r'^\s*(\d+),\s*-?\d+,\s*\d+,\w+,0x[0-9a-fA-F]+,(.*)$')


def words(addr, n):
    for _ in range(6):
        w = mem_get(addr, n)
        if None not in w:
            return w
    raise SystemExit(f'could not read 0x{addr:08X}')


def firmware_log(flag):
    out = []
    for line in sh(f'log out {flag}', retries=0).splitlines():
        m = LOG.match(line)
        if m:
            out.append((int(m.group(1)), f'{flag}: {m.group(2).strip()}'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=pathlib.Path)
    ap.add_argument('--logs', default='INIT,UI,DISP', help='firmware log flags to merge')
    a = ap.parse_args()

    magic, count, *stamps = words(MARK_DATA, 2 + MARK_SLOTS)
    start, done = words(LOAD_START_US, 2)
    path = {7: 'slow (store miss)', 5: 'Fast Start 3 (store hit)', 0: 'Fast Start 2 (warm, no AutoRun)'}
    events = [(stamps[i], LABELS[i] if count == 7 or i < 5 else f'S{i}') for i in range(min(count, MARK_SLOTS))]
    if start:
        events.append((start, 'loader entered (LOAD_START_US)'))
    if done:
        events.append((done, 'loader done (LOAD_DONE_US)'))
    for flag in filter(None, a.logs.split(',')):
        events += firmware_log(flag)
    events.sort()

    print(f'marker magic {MAGIC.get(magic, hex(magic))}, {count} stamps -> path: '
          f'{path.get(count, "unexpected count") if magic != 0x454E4F4E else path[0]}')
    if count >= 2:
        print(f'one marker costs {(stamps[1] - stamps[0]) / 1000:.2f} ms (S1 - S0)')
    prev = None
    for t, what in events:
        d = '' if prev is None else f'  (+{(t - prev) / 1000:.1f})'
        print(f'{t / 1000:9.1f} ms{d:>12}  {what}')
        prev = t
    if a.json:
        a.json.write_text(json.dumps(dict(magic=MAGIC.get(magic, magic), count=count,
                                          stamps=stamps[:count], load_start=start, load_done=done,
                                          events=events), indent=1))


if __name__ == '__main__':
    main()
