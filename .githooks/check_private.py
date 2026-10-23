#!/usr/bin/env python3
"""Pre-commit check: keep firmware and decompiler output out of the public repo.

Blocks a commit when a staged file
  - sits under a `private/` directory (added with `git add -f` past .gitignore);
  - carries 32 KiB or more of SIGMA fp firmware *code* (the first 24 MiB of
    MAIN). Sups legitimately carry copied UI resources from the data region
    above that, so those do not count;
  - looks like decompiler output: 20+ lines identical to the local Ghidra
    export, or 80+ `undefined4`/`undefined8`/`FUN_xxxxxxxx(` (research notes
    quoting a few snippets stay well under that).

The firmware image and the decompiler export stay on your machine. Point the
check at them once per clone (otherwise it looks for out/ two levels up):

    git config fpsup.firmware /path/to/out/MAIN_c0000000.bin
    git config fpsup.decomp   /path/to/out/decomp

Without the image the firmware check is skipped with a warning.
Bypass for one commit, when you are sure: git commit --no-verify
"""
import glob, hashlib, os, re, subprocess, sys

CODE_END = 24 << 20
MIN_CODE = 32 << 10
UNDEF = re.compile(rb'\bundefined[48]\b|\bFUN_[0-9a-fA-F]{8}\s*\(')


def git(*a, data=None):
    return subprocess.run(['git', *a], input=data, capture_output=True, check=False).stdout


def setting(key, fallback):
    v = git('config', '--get', key).decode().strip()
    if v:
        return v
    top = git('rev-parse', '--show-toplevel').decode().strip()
    for up in ('..', '../..', '../../..'):
        p = os.path.normpath(os.path.join(top, up, fallback))
        if os.path.exists(p):
            return p
    return None


def firmware_index(path):
    import numpy as np
    st = os.stat(path)
    tag = hashlib.sha1(f'{path}{st.st_size}{st.st_mtime}'.encode()).hexdigest()[:12]
    cache = os.path.expanduser(f'~/.cache/fpsup-precommit/code-{tag}.npy')
    if os.path.exists(cache):
        return np.load(cache)
    with open(path, 'rb') as f:
        code = f.read(CODE_END)
    k, ok = keys(code)
    idx = np.unique(k[ok])
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    np.save(cache, idx)
    return idx


def keys(b, phase=0):
    import numpy as np
    n = (len(b) - phase) // 4
    a = np.frombuffer(b, dtype='<u4', count=n, offset=phase).astype(np.uint64)
    if len(a) < 4:
        return np.zeros(0, np.uint64), np.zeros(0, bool)
    w0, w1, w2, w3 = a[:-3], a[1:-2], a[2:-1], a[3:]
    k = (w0 | (w1 << np.uint64(32))) * np.uint64(0x9E3779B97F4A7C15) ^ (w2 | (w3 << np.uint64(32)))
    ok = ((w0 != 0).astype(int) + (w1 != 0) + (w2 != 0) + (w3 != 0) >= 3) \
        & ~((w0 == w2) & (w1 == w3)) & (w0 != w1)
    return k, ok


def code_bytes(data, idx):
    import numpy as np
    best = 0
    for ph in range(4):
        k, ok = keys(data, ph)
        k = k[ok]
        if not len(k):
            continue
        j = np.searchsorted(idx, k)
        j[j >= len(idx)] = 0
        # distinct windows only: a log repeating one shell string must not add up
        best = max(best, len(np.unique(k[idx[j] == k])))
    return best * 4


def main():
    names = git('diff', '--cached', '--name-only', '--diff-filter=AMR', '-z').split(b'\0')
    names = [n.decode() for n in names if n]
    if not names:
        return 0
    problems = []
    for n in names:
        if re.search(r'(^|/)private/', n):
            problems.append((n, 'under a private/ directory'))

    fw = setting('fpsup.firmware', 'out/MAIN_c0000000.bin')
    idx = None
    if fw and os.path.exists(fw):
        try:
            idx = firmware_index(fw)
        except ImportError:
            print('fpsup pre-commit: numpy missing, firmware check skipped', file=sys.stderr)
    else:
        print('fpsup pre-commit: firmware image not found, firmware check skipped '
              '(git config fpsup.firmware <MAIN_c0000000.bin>)', file=sys.stderr)

    dlines = set()
    dec = setting('fpsup.decomp', 'out/decomp')
    if dec and os.path.isdir(dec):
        for f in glob.glob(os.path.join(dec, '**', '*'), recursive=True):
            if os.path.isfile(f):
                with open(f, errors='ignore') as fh:
                    dlines.update(l.strip() for l in fh if len(l.strip()) >= 40)

    for n in names:
        data = git('show', f':{n}')
        if idx is not None and len(data) >= 64:
            c = code_bytes(data, idx)
            if c >= MIN_CODE:
                problems.append((n, f'{c // 1024} KiB of firmware code'))
        if len(data) < 20_000_000:
            u = len(UNDEF.findall(data))
            d = sum(1 for l in data.decode('utf-8', 'ignore').splitlines() if l.strip() in dlines) if dlines else 0
            if u >= 80 or d >= 20:
                problems.append((n, f'looks like decompiler output ({u} undefined4/8 or FUN_ calls, {d} Ghidra lines)'))

    if not problems:
        return 0
    print('\nfpsup pre-commit: these files should not go into the public repo:\n', file=sys.stderr)
    for n, why in problems:
        print(f'  {n}\n      {why}', file=sys.stderr)
    print('\nMove them to a private/ directory (or the vendor folder outside the repo) and unstage:\n'
          '  git restore --staged <file>\n'
          'If you are sure, bypass once with: git commit --no-verify\n', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
