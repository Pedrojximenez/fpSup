"""Execute the real QS adapter against original native variable instructions."""
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT/'fpSup/loader-v4'), str(HERE.parent/'sup')]
import build_v4 as B
from test_native_input import InputProbe, N


class NativeSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            source = d/'adapter.c'
            source.write_text('#include "settings.h"\n'
                'int adapter_read(const struct qsn_native *a,const char *n,uint32_t *v)'
                '{return qsn_read(a,n,v);}\n'
                'int adapter_apply(const struct qsn_native *a,const char *n,uint32_t v,uint32_t count)'
                '{uint32_t r=0;return qsn_apply(a,n,v,count,&r)?(int)r:-1;}\n')
            cls.text = B.compile_unit(d, source, 'adapter_apply', ['-I', str(HERE)])

    def probe(self):
        p = InputProbe(dict(source='QS_Source', destination='MV_Resolution', source_type=0))
        self.addCleanup(p.close)
        base = p.SERVICES+0x1000
        p.uc.mem_map(base, (len(self.text.code)+4095)&~4095)
        p.uc.mem_write(base, self.text.code)
        original = p._instruction
        # Hook binding is established at construction, so extend its explicit
        # native allow-list; replacing the Python method would not rebind it.
        p.EXTRA = (*p.EXTRA, (base, base+len(self.text.code)))
        p.adapter_base = base
        p.api = p.zero(12)
        p.write_words(p.api, p.APP, N.registry.LOOKUP_APP|1, N.binding.SET_NOTIFY|1)
        return p

    def apply(self, p, value, count=8, name=None):
        return p.run(p.adapter_base+(self.text.functions['adapter_apply']&~1),
                     p.api, name or p.names['MV_Resolution'], value, count)

    def test_change_reaches_original_owner_and_returns_real_readback(self):
        p = self.probe()
        self.assertEqual(self.apply(p, 1), 1)
        self.assertEqual(p.events, [1])
        self.assertEqual(p.words(p.descs['MV_Resolution']+8)[0], 1)
        self.assertEqual(self.apply(p, 1), 1)
        self.assertEqual(p.events, [1], 'unchanged values must not trigger the native setter again')

    def test_out_of_range_and_missing_variable_never_write(self):
        p = self.probe()
        for value, count in ((8, 8), (0, 0), (0xFFFFFFFF, 8)):
            self.assertEqual(self.apply(p, value, count), 0xFFFFFFFF)
        unknown = p.zero(16);p.write(unknown, b'Missing\0')
        self.assertEqual(self.apply(p, 1, name=unknown), 0xFFFFFFFF)
        self.assertEqual(p.events, [])
        self.assertEqual(p.words(p.descs['MV_Resolution']+8)[0], 0)


if __name__ == '__main__':unittest.main(verbosity=2)
