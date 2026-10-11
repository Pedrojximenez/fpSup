"""Check exact record-matrix rate rounding for every mode and FPS row, offline."""
import ctypes as ct,json,pathlib,tempfile
import test_sl_modes as T

def run(report):
    cases=0;rates=(2398,2400,2500,2997,4800,5000,5994,10000,11988,23976)
    with tempfile.TemporaryDirectory(prefix='reslab-rate-audit-') as tmp:
        lib=T.build(tmp,calc_only=True);lib.slm_calc_seed.argtypes=[ct.c_uint32]*12
        lib.slm_calc_get.restype=ct.c_uint32;lib.slm_calc_rate.restype=ct.c_char_p
        T.Modes().camera(lib,rec_cap=(0,0));lib.slm_pages(0x56000000,0x57000000,123);lib.slm_ui(1)
        for mode in T.REG.modes:
            w,h=mode.raw;sx,sy=mode.scale
            for bh,bv in ((1,1),(3,1),(1,3),(3,3)):
                for crop in ((0,0),((w//2)&~15,(h//2)&~1),((w-64)&~15,(h-64)&~1)):
                    for index,fps in enumerate(rates):
                        lib.slm_panel_value(26,index+1)
                        lib.slm_calc_seed(mode.mid,w,h,sx,sy,bh,bv,*crop,16,w,h)
                        lib.slm_clear_posts();lib.slm_fit(1)
                        assert lib.slm_calc_get(11)==1
                        rw,rh=lib.slm_calc_get(32),lib.slm_calc_get(33)
                        bits=14 if mode.depth==14 else 12
                        mb=(rw*rh*bits*fps+400000000)//800000000
                        fpstext=str(fps//100)+(('.%02d'%(fps%100)) if fps%100 else '')
                        got=lib.slm_calc_rate().decode();want=f'{fpstext}p {mb} MB/s'
                        assert got==want,(mode.mid,index,crop,got,want)
                        cases+=1
    result={'modes':len(T.REG.modes),'fps_rows':10,'cases':cases,'passed':True}
    pathlib.Path(report).write_text(json.dumps(result,indent=2)+'\n');print(result)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);run(p.parse_args().report)
