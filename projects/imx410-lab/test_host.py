#!/usr/bin/env python3
"""imxl.py's offline half: records -> DNG files, including a file that spans
two records and a gap in the clusters.   python3 -B -m unittest test_host"""
import pathlib, struct, sys, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / 'sup')]
import imxl                                               # noqa: E402
import imxl_records as R                                  # noqa: E402

CL = 0x20000


def rec(seq, cl, data):
    head = R.REC.pack(R.REC_MAGIC, seq, cl, len(data), 3, 1000 * seq, 50, 4)
    return head + data + b'\0' * (-len(data) % 4)


def dng(tag, clusters):
    body = b'II*\0' + tag + bytes(CL * clusters - 4 - len(tag))
    return body


class HostTests(unittest.TestCase):
    def test_split(self):
        a, b, c = dng(b'A', 2), dng(b'B', 3), dng(b'C', 1)
        # record 0: a + first cluster of b; record 1: rest of b; record 2 after a gap: c
        r0 = a + b[:CL]
        r1 = b[CL:]
        stream = rec(0, 0x40, r0) + rec(1, 0x40 + 3, r1) + rec(2, 0x50, c)
        recs = list(R.records(stream, len(stream)))
        self.assertEqual([r['seq'] for r in recs], [0, 1, 2])
        with tempfile.TemporaryDirectory() as t:
            n = imxl.split_dngs(recs, pathlib.Path(t) / 'f')
            files = sorted((pathlib.Path(t) / 'f').iterdir())
            self.assertEqual(n, 3)
            self.assertEqual([f.read_bytes() for f in files], [a, b, c])

    def test_broken_chain_is_loud(self):
        stream = rec(0, 0x40, dng(b'A', 1))
        with self.assertRaises(ValueError):
            list(R.records(stream, len(stream) + 4))
        bad = bytearray(stream); bad[0] ^= 1
        with self.assertRaises(ValueError):
            list(R.records(bad, len(bad)))


if __name__ == '__main__':
    unittest.main()
