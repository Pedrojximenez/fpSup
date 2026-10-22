"""Compile/apply all 62 supported donors with the real two-Sup ARM path."""
import json,pathlib,time,sys
import test_virtual_rcd as V
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'sl_menu'))
import test_sl_modes as H

def run(report):
    started=time.monotonic();out,f=V.built();rows=[]
    modes=[m for m in H.REG.modes if m.depth!=14]
    test=V.VirtualTests('test_contract_abi_and_status');test.out,test.f=out,f
    for start in range(0,len(modes),24):
        # A fresh boot keeps this run inside the documented 32-pack budget.
        cam=test.boot(fr=12)
        for m in modes[start:start+24]:
            w,h=m.raw
            for key,value in {'crop_w':0,'crop_h':0,'ratio':0}.items():cam.set(key,value)
            cam.geometry(m.mid,w,h)
            cam.call(cam.fn('sl_modes__fit'),cam.m(),1,thumb=True,sp=V.T.STACK-0x1000)
            cam.call(cam.fn('sl_modes__panel_post'),cam.m(),thumb=True,sp=V.T.STACK-0x1000)
            aw,ah=cam.get('out_w'),cam.get('out_h')
            generation=cam.w(cam.service()+16)
            assert cam.apply()==0,(m.mid,aw,ah,cam.w(cam.service()+20),cam.w(cam.service()+24))
            assert cam.w(cam.service()+16)==generation+1
            assert (cam.w(cam.row()+V.L.ROW['AW']),cam.w(cam.row()+V.L.ROW['AH']))==(aw,ah)
            assert cam.w(cam.s()+V.L.S['FLAG'])==1
            assert cam.w(cam.s()+V.L.S['NROWS'])==1
            cam.assert_tables(test);assert not cam.misaligned
            rows.append({'mode':m.mid,'output':[aw,ah],'generation':generation+1,
                         'pack_count':cam.w(cam.service()+32),'result':0})
            print('M%d applied %dx%d'%(m.mid,aw,ah),flush=True)
    result={'module_sha256':json.loads((out/'build.json').read_text())['sha256'],
            'modes':rows,'cases':len(rows),'emulated_fps_enum':12,'passed':True,
            'seconds':round(time.monotonic()-started,3)}
    pathlib.Path(report).write_text(json.dumps(result,indent=2)+'\n');print('PASS',len(rows),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);run(p.parse_args().report)
