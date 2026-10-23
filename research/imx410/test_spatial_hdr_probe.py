#!/usr/bin/env python3
"""Execute real stock v10 and its guarded clone offline; never opens USB."""
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as R

import spatial_hdr_probe as P

G = 0xC343B588
CAL = 0xC2F1E654
AT = 0xC072E428
STACK = 0x10000000
STOP = 0x10100000


def execute(*, cloned=True, enabled=True, a=985, b=2540, requested=985,
            expected=985, mode=102, gain_state=7, cg=0, cinema=1,
            applied_cinema=1, maximum=0xF7F, suppress=0,
            raw_config=None, mutation=None):
    code, meta = P.build(AT)
    if mutation:
        code = mutation(code, meta)
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0xC0000000, 0x04000000)
    uc.mem_map(STACK, 0x10000)
    uc.mem_map(STOP, 0x1000)
    uc.mem_write(P.ORIGINAL, P.stock_code())
    uc.mem_write(AT, code)

    def put(addr, value):
        uc.mem_write(addr, struct.pack('<I', value))

    put(G, CAL)
    put(CAL+0x54, maximum)
    put(G+4, mode)
    put(G+0x34, cg)
    put(0xC31C01B0, cinema)
    put(0xC31F86E0, applied_cinema)
    put(0xC343A6AC, gain_state)
    put(meta['state']+4, (P.config(a,b) if enabled else 0)
        if raw_config is None else raw_config)
    put(meta['state']+8, expected)
    saved = {getattr(R,f'UC_ARM_REG_R{n}'):0x12340000+n for n in range(4,12)}
    for reg,value in saved.items():
        uc.reg_write(reg,value)
    uc.reg_write(R.UC_ARM_REG_SP,STACK+0xFFF0)
    uc.reg_write(R.UC_ARM_REG_LR,STOP)
    uc.reg_write(R.UC_ARM_REG_R0,G)
    uc.reg_write(R.UC_ARM_REG_R1,requested)
    writes=[]
    returned=[]

    def hook(uc,address,size,_):
        if address==STOP:
            returned.append(True)
            uc.emu_stop()
            return
        if address in (P.WRITER,P.SUPPRESS):
            assert uc.reg_read(R.UC_ARM_REG_SP)%8==0, 'unaligned native call'
            result=suppress if address==P.SUPPRESS else 0xAABBCCDD
            if address==P.WRITER:
                writes.append((uc.reg_read(R.UC_ARM_REG_R0),uc.reg_read(R.UC_ARM_REG_R1)))
            lr=uc.reg_read(R.UC_ARM_REG_LR)
            for n in (0,1,2,3,12):
                uc.reg_write(getattr(R,f'UC_ARM_REG_R{n}'),0xBAD00000+n)
            uc.reg_write(R.UC_ARM_REG_R0,result)
            uc.reg_write(R.UC_ARM_REG_PC,lr)
            return
        if not (P.ORIGINAL<=address<P.END or AT<=address<meta['state']):
            raise AssertionError(f'unreviewed execution: {address:#x}')

    uc.hook_add(UC_HOOK_CODE,hook)
    uc.emu_start(AT if cloned else P.ORIGINAL,STOP+4,count=10000)
    assert returned, 'v10 failed to return'
    assert uc.reg_read(R.UC_ARM_REG_R0)==1, 'v10 return changed'
    assert uc.reg_read(R.UC_ARM_REG_SP)==STACK+0xFFF0, 'stack not restored'
    for reg,value in saved.items():
        assert uc.reg_read(reg)==value, 'callee-saved register changed'
    state=struct.unpack('<12I',uc.mem_read(meta['state'],48))
    actual=struct.unpack('<I',uc.mem_read(G+0x20,4))[0]
    return writes,state,actual


class ProbeTests(unittest.TestCase):
    def test_disabled_matches_real_stock_across_all_original_branches(self):
        for cg in (0,1):
            for requested in (0,985,3580,3581,3900,0xFFFF):
                for suppress in (0,1):
                    with self.subTest(cg=cg,requested=requested,suppress=suppress):
                        args=dict(cg=cg,requested=requested,suppress=suppress,enabled=False)
                        stock=execute(cloned=False,**args)
                        probe=execute(**args)
                        self.assertEqual(stock[0],probe[0])
                        self.assertEqual(stock[2],probe[2])

    def test_all_four_gain_combinations(self):
        stock=execute(cloned=False)[0]
        for a,b in ((985,985),(2540,985),(985,2540),(2540,2540)):
            with self.subTest(a=a,b=b):
                writes,state,actual=execute(a=a,b=b)
                self.assertEqual(writes[:-4],stock[:-4])
                self.assertEqual(writes[-4:],[(0x3D,a&255),(0x3E,a>>8),
                                               (0x3F,b&255),(0x40,b>>8)])
                self.assertEqual(actual,985)
                self.assertEqual(state[3:5],(4,4))
                self.assertEqual(state[5],P.config(a,b))
                self.assertEqual(state[7],0)
                self.assertEqual(state[10:12],(1,1))

    def test_rejected_contexts_are_exact_stock_writes(self):
        cases=[dict(mode=8),dict(mode=6),dict(gain_state=0),dict(gain_state=5),
               dict(cg=1),dict(cinema=0),dict(applied_cinema=0),dict(expected=984),
               dict(maximum=2000),dict(raw_config=0x81000000|985|(2540<<12)),
               dict(raw_config=0x80000000|985|(0xDFD<<12))]
        for args in cases:
            with self.subTest(args=args):
                stock=execute(cloned=False,**args)[0]
                writes,state,_=execute(**args)
                self.assertEqual(writes,stock)
                self.assertEqual(state[4],0)
                self.assertNotEqual(state[7],0)

    def test_host_code_range_guards(self):
        for a,b in ((-1,985),(985,0xDFD),(4095,0),(True,0)):
            with self.assertRaises(ValueError):P.config(a,b)
        with self.assertRaises(ValueError):P.build(0x45000000)
        with self.assertRaises(ValueError):P.arm_bl(0x1000,0x45000000)

    def test_no_pc_relative_data_in_stock_clone(self):
        from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
        for insn in Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(P.stock_code(),P.ORIGINAL):
            self.assertFalse(insn.mnemonic=='adr' or
                             (insn.mnemonic.startswith('ldr') and 'pc' in insn.op_str))

    def test_mutations_break_the_relevant_assertion(self):
        def remove_mode_guard(blob,meta):
            out=bytearray(blob)
            needle=struct.pack('<I',0xE3520066) # cmp r2,#102
            off=out.index(needle,meta['helper']-AT)
            out[off:off+4]=struct.pack('<I',0xE320F000)
            return bytes(out)
        writes,_,_=execute(mode=8,mutation=remove_mode_guard)
        with self.assertRaises(AssertionError):
            self.assertEqual(writes,execute(cloned=False,mode=8)[0])

        def corrupt_bank_boundary(blob,meta):
            out=bytearray(blob)
            needle=struct.pack('<I',0xE356003F) # cmp r6,#0x3F
            off=out.index(needle,meta['helper']-AT)
            out[off:off+4]=struct.pack('<I',0xE3560041)
            return bytes(out)
        writes,_,_=execute(mutation=corrupt_bank_boundary)
        with self.assertRaises(AssertionError):
            self.assertEqual(writes[-2:],[(0x3F,2540&255),(0x40,2540>>8)])

        def unalign_stack(blob,meta):
            out=bytearray(blob)
            off=meta['helper']-AT
            self.assertEqual(struct.unpack_from('<I',out,off)[0],0xE92D41F0)
            struct.pack_into('<I',out,off,0xE92D40F0)
            return bytes(out)
        with self.assertRaisesRegex(AssertionError,'unaligned native call'):
            execute(mutation=unalign_stack)


if __name__=='__main__':
    unittest.main(verbosity=2)
