"""Actual calculator canvas -> firmware CRCT selector, including M12 AUTO.

The selector runs from the firmware image; it is not a copied formula model.
No camera or hardware registers are accessed.
"""
import hashlib, json, struct, unittest
import test_virtual_rcd as V
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP,
                               UC_ARM_REG_LR, UC_ARM_REG_PC)

OFFSETS=(0,4,12,16,28,32,36,40,44,56,88,92,96,100,136,144,192,196,200,208,212,216,220,224,228,244,248,252,256)

def native_engine_gate(cam, canvas):
    """Real canvas translator, FPS publication prefix and >99 engine gate.

    OS/capability queries are fixed stubs. Stop the publication routine after
    its FPS/film fields are copied, before hardware configuration. This does
    not model DMA, sensor cadence or prove a clean recording on the camera.
    """
    holder,cfg,app=V.RC.KEYBUF+0x2000,V.RC.KEYBUF+0x2200,V.RC.KEYBUF+0x2600
    cam.mu.mem_write(holder,bytes(0x60));cam.put(holder+4,canvas)
    cam.mu.mem_write(cfg,bytes(0x1b0));cam.mu.mem_write(app,bytes(0x200))
    for start,end,step in ((0xc0434ef8,0xc0435428,4),
                           (0xc01d1630,0xc01d1728,2),
                           (0xc01cec08,0xc01cec30,2),
                           (0xc01d34f0,0xc01d3518,2)):
        cam.mu.mem_write(start,cam.img[start-0xc0000000:end-0xc0000000])
        cam.test_code.update(range(start,end,step))
    # Native translator's model/capability lookups and the publication
    # prefix's channel flags have no effect on the FPS copy being tested.
    for at,value in ((0xc00178d8,0),(0xc0017ac8,app),(0xc032c900,0),
                     (0xc01d8638,0),(0xc01ca800,0)):
        thumb=at in (0xc01d8638,0xc01ca800)
        code=struct.pack('<HHI',0x4800,0x4770,value) if thumb else struct.pack('<3I',0xe59f0000,0xe12fff1e,value)
        cam.mu.mem_write(at,code);cam.by_addr.pop(at,None)
        cam.test_code.update(range(at,at+len(code),2 if thumb else 4))
    cam.mu.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000)
    cam.mu.reg_write(UC_ARM_REG_FPEXC,0x40000000)
    cam.call(0xc0434ef8,r0=holder,r1=cfg,sp=V.T.STACK-0x1000)
    cam.mu.reg_write(UC_ARM_REG_R0,0);cam.mu.reg_write(UC_ARM_REG_R1,cfg)
    cam.mu.reg_write(UC_ARM_REG_SP,V.T.STACK-0x1000)
    cam.mu.reg_write(UC_ARM_REG_LR,V.T.DONE)
    cam.mu.emu_start(0xc01d1631,0xc01d1728,count=1000)
    if cam.error:raise cam.error
    assert cam.r(UC_ARM_REG_PC)==0xc01d1728
    assert cam.w(cfg+0x10)==cam.w(canvas+0x30)==cam.w(0xc31df574)
    result,_=cam.call(0xc01cec08,r0=0,thumb=True,sp=V.T.STACK-0x1000)
    return result

def native_route(cam, canvas, raw_bit=0):
    inp,out=V.RC.KEYBUF+0x1000,V.RC.KEYBUF+0x1100
    cam.mu.mem_write(inp,bytes(0x38));cam.mu.mem_write(out,bytes(0x4c))
    # C031D988 initializes these defaults before calling the selector. Its
    # +0x18 input is RAW bit kind (0=12, 3=10, 4=8), NOT PARAM +0x1c class.
    for o,v in ((4,1),(8,1),(12,1),(16,1),(24,1),(28,2),
                (36,1),(40,1),(44,1),(48,1),(52,1024),(56,1024),(60,1024),(64,1024)):
        cam.put(out+o,v)
    for o,v in ((0,canvas[0]),(4,canvas[4]),(8,max(1024,canvas[0x64])),(12,max(1024,canvas[0xd4])),
                (16,(1,3,5)[canvas[0x5c]]),(20,(1,3,5)[canvas[0xc8]]),(24,raw_bit),
                (28,canvas[0xc]),(32,canvas[0x10]),
                (36,max(1024,canvas[0x60])),(40,max(1024,canvas[0xd0])),
                (44,(1,3,5)[canvas[0x58]]),(48,(1,3,5)[canvas[0xc4]])):
        cam.put(inp+o,v)
    # The fixture normally forbids ROM execution except explicit boundaries.
    # This pure selector has no external calls. Restore the exact ROM bytes.
    address=0xc0325228;end=0xc03255b0
    cam.mu.mem_write(address,cam.img[address-0xc0000000:end-0xc0000000])
    cam.test_code.update(range(address,end,4))
    cam.call(address,r0=0xc343b588,r1=inp,r2=out)
    data=bytes(cam.mu.mem_read(out,0x4c))
    return {'enabled':list(data[:3]),'mux':list(struct.unpack_from('<2I',data,4)),
            'main_zoom':list(struct.unpack_from('<2I',data,0x34)),
            'secondary_zoom':list(struct.unpack_from('<2I',data,0x3c)),
            'record':struct.unpack_from('<I',data,0x48)[0]}

class PreviewRouteTests(unittest.TestCase):
    def test_m12_r78_geometry_survives_virtual_rcd_and_native_selection(self):
        out,f=V.built();test=V.VirtualTests('test_contract_abi_and_status');test.out,test.f=out,f
        cam=test.boot(fr=3)
        root=V.HERE.parents[2]
        evidence=root/'projects/res-lab/validation/20261009-recording-formula/frozen-r78.json'
        old=json.loads(evidence.read_text())
        blob=root/'projects/res-lab/cards/20261004-b25-menu-r78-isopreview/fast-debug/fpSup.BIN'
        self.assertEqual(hashlib.sha256(blob.read_bytes()).hexdigest(),old['sha256'])
        profiles=json.loads((root/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
        base=next(r['words'] for r in profiles['rows'] if 83 in r['profile_ids'])
        cam.geometry(12,992,662)
        vals=struct.unpack('<29I',cam.mu.mem_read(cam.m()+f['state_fields']['canvas'],116))
        canvas=dict(zip(OFFSETS,vals))
        self.assertEqual(canvas,{int(k,0):v for k,v in old['canvas'].items()})
        self.assertEqual(f['state_fields']['mode_ids'],f['state_fields']['axis_armed']+12)
        self.assertEqual([cam.w(cam.m()+f['state_fields']['axis_armed']+o) for o in (4,8)],old['standby'])
        self.assertEqual(cam.apply(),0)
        cam.mu.mem_write(V.RC.KEYBUF,b'VRC00030\0'.ljust(16,b'\0'))
        hit,_=cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)
        self.assertNotEqual(hit,0)
        pid=cam.w(hit+4)
        native=V.RC.CANVAS_IN+0x5c
        cam.mu.mem_write(native,struct.pack('<65I',*base))
        fn=cam.w(cam.s()+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
        self.assertEqual(cam.call(fn,cam.s(),native,pid,thumb=True,sp=V.T.STACK-0x1000)[0],1)
        got=list(struct.unpack('<65I',cam.mu.mem_read(native,260)))
        expected=list(old['row'])
        for o,v in old['recipe_canvas'].items():expected[int(o,0)//4]=v
        # res-custom uses the stock nominal 30.0 engine field; r78 used
        # 30000/1001 here. Timing words, which drive the sensor, must match.
        self.assertEqual(got[0x30//4],struct.unpack('<I',struct.pack('<f',30.0))[0])
        entry=cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT'])
        self.assertEqual((cam.w(entry+V.L.ENT['W0']),cam.w(entry+V.L.ENT['W1'])),tuple(old['recipe'][12:14]))
        expected[0x30//4]=got[0x30//4]
        # Both unity encodings clamp to 1024 in the native caller.
        for o in (0x60,0x64,0xd0,0xd4):
            got[o//4]=max(1024,got[o//4]);expected[o//4]=max(1024,expected[o//4])
        self.assertEqual(got,expected,'profile differs from frozen r78 beyond nominal FPS / unity encoding')
        route=native_route(cam,canvas)
        self.assertEqual(route['enabled'],[0,0,1])
        self.assertEqual(route['mux'],[1,3])
        self.assertEqual(route['record'],1)
        self.assertEqual(route['main_zoom'],[2048,1024])
        print('M12: 29 producer fields, standby region and 64 geometry/profile words and sensor timing match r78 (nominal FPS encoding differs); native route',route,flush=True)

        # A geometrically bounded v11 canvas must still be rejected: it
        # reintroduces the unequal preview known to show the start-up seam.
        fields=f['state_fields'];start=cam.m()+fields['canvas']
        for index,value in ((2,1008),(5,992),(12,2048),(21,1008)):
            cam.put(start+index*4,value)
        label=V.RC.KEYBUF+0x1200;cam.mu.mem_write(label,b'VRC000\0')
        self.assertEqual(cam.call(cam.fn('rl_encode'),cam.m(),label,thumb=True,sp=V.T.STACK-0x1000)[0],0)

    def test_binning_keeps_its_matching_native_tap(self):
        out,f=V.built();test=V.VirtualTests('test_contract_abi_and_status');test.out,test.f=out,f
        cam=test.boot()
        cam.geometry(7,1248,1124,3,1)
        vals=struct.unpack('<29I',cam.mu.mem_read(cam.m()+f['state_fields']['canvas'],116))
        canvas=dict(zip(OFFSETS,vals));route=native_route(cam,canvas)
        self.assertEqual(route['enabled'],[0,1,0])
        self.assertEqual(route['mux'],[1,4])
        self.assertEqual(route['record'],0)
        self.assertEqual(cam.apply(),0)

if __name__=='__main__':unittest.main()
