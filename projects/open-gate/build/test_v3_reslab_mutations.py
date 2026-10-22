#!/usr/bin/env python3
"""Bounded calculator safety mutations, compiled from isolated C copies.

The expected outcome is an assertion failure, not an emulator exception.
No camera and no mutation of the maintained sources.
"""
import argparse
import contextlib
import hashlib
import io
import json
import pathlib
import tempfile
import unittest

import build_v3_reslab as B
import test_v3_reslab as T


class Check(T.CalculatorTests):
    def test_corrupt_readback_is_refused(self):
        cam = self.boot(damage=True)
        cam.prepare()
        cam.geometry()
        self.assertEqual(cam.export(), 5, 'corrupt readback must report failure')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--card', type=pathlib.Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = (B.HERE / 'rl_v3.c').read_text()
    variants = (
        ('unclaimed-sensor-write', '    (void)path;',
         '    (void)path; rl_wr(0xC0BF0000u,0x58585959u);', 'test_no_recording_core_and_restoration'),
        ('unchecked-readback', 'if (a[i]!=b[i]) ok=0;',
         'if (a[i]!=b[i]) (void)0;', 'test_corrupt_readback_is_refused'),
    )
    report = []
    original_here = B.HERE
    try:
        for name, old, new, test in variants:
            if source.count(old) != 1:
                raise RuntimeError(f'{name}: mutation anchor changed')
            with tempfile.TemporaryDirectory(prefix='rlcalc-mut-') as d:
                tmp = pathlib.Path(d)
                src = tmp / 'source'
                src.mkdir()
                mutated = source.replace(old, new)
                (src / 'rl_v3.c').write_text(mutated)
                B.HERE = src
                data, facts = B.build(tmp)
                T._CACHE.clear()
                T._CACHE.update(sup=data, facts=facts, out=args.card.resolve())
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite([Check(test)]))
                (args.out / f'mutation-{name}.log').write_text(stream.getvalue())
                caught = result.testsRun == 1 and len(result.failures) == 1 and not result.errors
                report.append(dict(name=name, detected=caught, tests=result.testsRun,
                    failures=len(result.failures), errors=len(result.errors),
                    source_sha256=hashlib.sha256(mutated.encode()).hexdigest(),
                    sup_sha256=hashlib.sha256(data).hexdigest()))
                print(f'{name}: {"detected" if caught else "NOT DETECTED"}', flush=True)
    finally:
        B.HERE = original_here
    (args.out / 'mutations.json').write_text(json.dumps(report, indent=2) + '\n')
    if not all(x['detected'] for x in report):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
