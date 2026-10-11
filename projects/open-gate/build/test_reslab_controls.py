"""Expanded controls and RCD CRCT recipes, using the real compiled ARM."""
import struct
import unittest
import test_virtual_rcd as V
import test_reslab_preview_route as PR
import rcd
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4, UC_ARM_REG_SP


class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.out,cls.f=V.built()
    def boot(self): return V.VirtualTests.boot(self,rcds={})
    def change(self,c,name,value):
        d=c.vars[name];c.put(d+8,value);c.call(c.subs[name],d,thumb=True,sp=V.T.STACK-0x1000)
    def key(self,c,key): self.change(c,'SL_O_Key',key)
    def ids(self,c): return list(c.mu.mem_read(c.m()+self.f['state_fields']['mode_ids'],c.get('modes_rows')))

    def test_filters_cover_sensor_areas_width_buckets_and_stable_sort(self):
        c=self.boot();all12=set(self.ids(c));self.assertIn(12,all12)
        groups=[]
        for area in range(1,7):
            self.change(c,'SL_F_Crop',area);groups.append(set(self.ids(c)))
            if area<6:self.assertTrue(groups[-1],area)
        self.assertEqual(set.union(*groups),all12)
        self.assertEqual(sum(map(len,groups)),len(all12))
        self.change(c,'SL_F_Crop',0)
        for level,threshold in ((1,2850),(2,3800),(3,5700)):
            self.change(c,'SL_F_Width',level)
            expected={m for m in all12 if c.w(0xC0B59DC0+100*c.modes.index(m)+4)>=threshold}
            self.assertEqual(set(self.ids(c)),expected)
        self.change(c,'SL_F_Width',0)
        self.change(c,'SL_M_Sel',self.ids(c).index(12))
        for order in (1,2,0):
            self.change(c,'SL_F_Prop',order)
            self.assertEqual(self.ids(c)[c.get('mode_sel')],12)
            self.assertEqual(set(self.ids(c)),all12)
        self.change(c,'SL_F_Fps',11)
        self.assertIn(12,self.ids(c))
        self.change(c,'SL_F_Fps',0);self.change(c,'SL_F_Bit',1)
        all14=set(self.ids(c));self.assertTrue(all14);self.assertFalse(all12&all14)
        for m in all14:self.assertEqual(c.w(0xC0B59DC0+100*c.modes.index(m)+0x3c),1)

    def test_output_lock_free_auto_and_crop_lock_are_separate(self):
        c=self.boot();c.geometry(12,992,662)
        self.assertEqual(c.w(c.vars['SL_O_Auto']+8),1)
        self.key(c,35);self.key(c,32);self.key(c,32);self.key(c,33)
        self.assertEqual(c.get('output_policy'),1)
        ratio=c.get('out_w')/c.get('out_h')
        self.key(c,32);self.key(c,34)
        self.assertAlmostEqual(c.get('out_w')/c.get('out_h'),ratio,delta=.02)
        self.key(c,31);self.key(c,33)
        self.assertEqual(c.get('output_policy'),2)
        self.key(c,32);h=c.get('out_h');self.key(c,34)
        self.assertEqual(c.get('out_h'),h)
        self.key(c,36)
        self.key(c,15);self.key(c,12);self.key(c,12);before=c.get('crop_lock');self.key(c,13)
        self.assertEqual(c.get('crop_lock'),1-before);self.key(c,16)
        self.assertEqual(c.get('output_policy'),2)
        self.change(c,'SL_O_Lens',9)
        self.assertEqual((c.get('lens_on'),c.get('lens_factor')),(9,200))
        c.geometry(8,2000,1334)
        self.key(c,35);self.key(c,32);self.key(c,32)
        for _ in range(4):
            self.key(c,33);self.assertIn(c.get('output_policy'),(1,2))
            self.assertEqual(c.w(c.vars['SL_O_Auto']+8),0)

    def test_each_fps_rate_uses_record_matrix_and_current_bit_depth(self):
        c=self.boot()
        fps=(2398,2400,2500,2997,4800,5000,5994,10000,11988,23976,27972)
        mode14=next(m for m in c.modes if c.w(0xC0B59DC0+100*c.modes.index(m)+0x3c)==1)
        for mode,w,h in ((12,992,662),(98,1504,1006),(8,2000,1334),(mode14,2000,1334)):
            c.geometry(mode,w,h)
            before=c.snapshot();generation=c.w(c.service()+16)
            matrix=struct.unpack('<2I',c.mu.mem_read(c.m()+self.f['state_fields']['canvas'],8))
            bits=14 if c.w(0xC0B59DC0+100*c.modes.index(mode)+0x3c)==1 else 12
            for i,rate in enumerate(fps):
                expected=(matrix[0]*matrix[1]*bits*rate+400000000)//800000000
                label=f'{rate/100:.2f}'.rstrip('0').rstrip('.')
                self.change(c,'SL_O_RFps',i)
                text=c.cstr(c.w(c.vars['SL_O_Rate']+8))
                self.assertEqual(text,f'{label}p {expected} MB/s')
                self.assertEqual(c.snapshot(),before)
                self.assertEqual(c.w(c.service()+16),generation)
        self.assertEqual(c.misaligned,[])

    def test_binning_recipe_survives_save_commit_and_real_driver_shims(self):
        c=self.boot();c.geometry(7,1248,1124,3,3)
        c.set('bin_kh',4);c.set('bin_kv',2);c.set('bin_mode',1)
        self.assertEqual(c.apply(),0)
        c.mu.mem_write(V.RC.KEYBUF,b'VRC00024\0'.ljust(16,b'\0'))
        self.assertNotEqual(c.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)[0],0)
        cfg_at=c.s()+V.L.S['BINFILT']+4*(c.w(c.s()+V.L.S['CUR'])-1)
        self.assertEqual(c.w(cfg_at),0xf24)
        self.assertEqual(c.export(),1)
        blob=c.written['\\fpSup\\RESCUS\\LAB001.RCD']
        self.assertEqual(rcd.decode(blob)['binning'],(3,3,4,2,1))
        # Full writer shims: only the native register writer is stubbed.
        driver=V.RC.KEYBUF+0x1800
        for site,target in ((0xc032ddf0,0xc0635db0),(0xc032de70,0xc0635dc8)):
            seen=[]
            # A BL hook returns to its real caller's next instruction.
            c.mu.mem_write(site+4,struct.pack('<2I',0xe51ff004,V.T.DONE));c.test_code.add(site+4)
            c.mu.mem_write(target,struct.pack('<H',0x4770));c.test_code.add(target)
            from unicorn import UC_HOOK_CODE
            hook=c.mu.hook_add(UC_HOOK_CODE,lambda mu,a,n,d:seen.append((c.r(UC_ARM_REG_R0),c.r(UC_ARM_REG_R1),c.r(UC_ARM_REG_SP))) if a==target else None)
            hside=(21,16,11,8,4,0);vside=(1365,1024,683,512,256,0)
            for k in range(6):
                c.put(cfg_at,0xe00|k|(k<<4));c.mu.mem_write(driver,b'\xa5'*64)
                regs=V.RC.Cam.callr(c,site,r0=0x1234,r1=driver,r4=0x5678,sp=V.T.STACK-0x1000)
                self.assertEqual((regs['r0'],regs['r1'],regs['r4']),(0x1234,driver,0x5678))
                data=bytes(c.mu.mem_read(driver,64))
                self.assertEqual(data[0x29:0x2c],bytes((hside[k],64-2*hside[k],hside[k])))
                self.assertEqual(data[0x1c:0x28],data[0x29:0x2c]*4)
                self.assertEqual(struct.unpack('<9H',data[8:26]),(vside[k],4096-2*vside[k],vside[k])*3)
                self.assertEqual(data[:8]+data[26:28]+data[40:41]+data[44:],b'\xa5'*31)
            self.assertEqual(len(seen),6);self.assertTrue(all(not sp&7 for _,_,sp in seen))
            c.mu.hook_del(hook)
        # Exact ROM selector with the installed hook retained.
        # This 3x1 geometry is a confirmed branch-C case; 3x3 can select a
        # different native branch, where main hbin=3 is the only reduction.
        c.geometry(7,1248,1124,3,1);self.assertEqual(c.apply(),0)
        self.assertNotEqual(c.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)[0],0)
        installed=bytes(c.mu.mem_read(0xc0325228,4))
        vals=struct.unpack('<29I',c.mu.mem_read(c.m()+self.f['state_fields']['canvas'],116))
        canvas=dict(zip(PR.OFFSETS,vals))
        route=PR.native_route(c,canvas);self.assertEqual(route['mux'],[1,4])
        c.mu.mem_write(0xc0325228,installed)
        c.mu.ctl_remove_cache(0xc0325228,0xc03255b0)
        inp,out=V.RC.KEYBUF+0x1000,V.RC.KEYBUF+0x1100
        for mode in (0,1):
            c.put(cfg_at,0xa00|(mode<<8))
            c.call(0xc0325228,r0=0xc343b588,r1=inp,r2=out,sp=V.T.STACK-0x1000)
            detail=dict(flags={n:c.w(c.s()+V.L.S[n]) for n in ('FLAG','PICKOK','CUR','NROWS')},cfg=c.w(cfg_at),input=list(struct.unpack('<14I',c.mu.mem_read(inp,56))),output=list(struct.unpack('<19I',c.mu.mem_read(out,76))))
            self.assertEqual(c.w(out+0x24),1,detail)
            self.assertEqual(c.w(out+0x48),mode)
        c.put(c.s()+V.L.S['FLAG'],0);c.mu.mem_write(driver,b'\xa5'*64)
        V.RC.Cam.callr(c,0xc032ddf0,r0=0x1234,r1=driver,sp=V.T.STACK-0x1000)
        self.assertEqual(bytes(c.mu.mem_read(driver,64)),b'\xa5'*64)
        c.call(0xc0325228,r0=0xc343b588,r1=inp,r2=out,sp=V.T.STACK-0x1000)
        self.assertEqual(c.w(out+0x24),3,'disabled custom format must pass the original route')
        # Bypass the hook in this emulator only: our double-binning assertion
        # must detect that mutation, not merely trust the recipe's metadata.
        c.put(c.s()+V.L.S['FLAG'],1)
        c.mu.mem_write(0xc0325228,c.img[0x325228:0x32522c])
        c.mu.ctl_remove_cache(0xc0325228,0xc03255b0)
        c.call(0xc0325228,r0=0xc343b588,r1=inp,r2=out,sp=V.T.STACK-0x1000)
        with self.assertRaises(AssertionError):self.assertEqual(c.w(out+0x24),1)
        c.mu.mem_write(0xc0325228,installed)
        c.mu.ctl_remove_cache(0xc0325228,0xc03255b0)
        bad=bytearray(blob)
        for i in range(struct.unpack_from('<I',bad,V.L.RCD['NSEC'])[0]):
            typ,off,length,flags=struct.unpack_from('<4I',bad,V.L.RCD_HDR+16*i)
            if typ==V.L.SEC_BINFILT:struct.pack_into('<I',bad,off+8,6);break
        bad=rcd.reseal(bad)
        with self.assertRaisesRegex(rcd.RcdError,'BINFILT'):rcd.decode(bad)
        old=c.snapshot();ident=c.blob_provider(bad)
        self.assertEqual(c.dispatch(2,ident),6)
        self.assertEqual(c.w(c.service()+24),V.L.RCD_WHY['BINFILT']);self.assertEqual(c.snapshot(),old)
        c.power_off()
        for h in c.cf['hooks']:
            at=int(h['site'],16);self.assertEqual(c.w(at),V.T.word(c.img,at))


if __name__=='__main__':unittest.main()
