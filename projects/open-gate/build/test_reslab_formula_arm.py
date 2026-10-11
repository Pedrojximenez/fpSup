"""Check each real ARM calculator mode against the host C and physical bounds."""
import argparse,ctypes as ct,json,pathlib,struct,tempfile,time
import test_virtual_rcd as V
import test_v3_reslab as RL
import rcd
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'sl_menu'))
import test_sl_modes as H

def run(report,limit=None):
 start=time.monotonic();out,f=V.built();test=V.VirtualTests('test_contract_abi_and_status')
 test.out,test.f=out,f;cam=test.boot()
 summary={'card':str(out),'module_sha256':json.loads((out/'build.json').read_text())['sha256'],
          'modes':{},'cases':0,'encoded':0,'raw14_rejected':0,'passed':False}
 with tempfile.TemporaryDirectory(prefix='reslab-arm-reference-') as tmp:
  lib=H.build(tmp,calc_only=True);lib.slm_calc_seed.argtypes=[ct.c_uint32]*12
  lib.slm_calc_get.argtypes=[ct.c_uint32];lib.slm_calc_get.restype=ct.c_uint32
  lib.slm_calc_rate.restype=ct.c_char_p
  fixture=H.Modes();fixture.camera(lib,rec_cap=(0,0));lib.slm_pages(0x56000000,0x57000000,123);lib.slm_ui(1)
  for mode in H.REG.modes:
   w,h=mode.raw;sx,sy=mode.scale;proof=[]
   cases=[(bh,bv,ratio,0,0,w,h,1) for bh,bv in ((1,1),(3,1),(1,3),(3,3)) for ratio in (0,1,7,16)]
   cases += [(3,3,ratio,(w-64)&~15,(h-64)&~1,16,2,lead) for ratio in (0,2,7,16) for lead in (0,1)]
   cases += [(1,1,16,0,0,(w//2)&~15,(h//2)&~1,1)]
   for bh,bv,ratio,cw,ch,ow,oh,lead in cases:
    if limit is not None and summary['cases']>=limit:break
    lib.slm_calc_seed(mode.mid,w,h,sx,sy,bh,bv,cw,ch,ratio,ow,oh)
    lib.slm_clear_posts();lib.slm_fit(lead)
    expected=[lib.slm_calc_get(i) for i in range(12)]
    canvas=[lib.slm_calc_get(32+i) for i in range(29)]
    values={'modes_rows':1,'mode_sel':0,'ro_w':w,'ro_h':h,'ro_sx':sx,'ro_sy':sy,
            'bin_h':bh,'bin_v':bv,'crop_w':cw,'crop_h':ch,'ratio':ratio,
            'out_w':ow,'out_h':oh,'axis_armed':1}
    for key,value in values.items():cam.set(key,value)
    cam.mu.mem_write(cam.m()+f['state_fields']['mode_ids'],bytes([mode.mid]))
    cam.call(cam.fn('sl_modes__fit'),cam.m(),lead,thumb=True,sp=V.T.STACK-0x1000)
    cam.call(cam.fn('sl_modes__panel_post'),cam.m(),thumb=True,sp=V.T.STACK-0x1000)
    got=[cam.get(k) for k in ('out_w','out_h','bin_h','bin_v','crop_w','crop_h','ratio')]
    assert got==expected[:7],(mode.mid,(bh,bv,ratio,cw,ch,ow,oh,lead),got,expected)
    native_canvas=list(struct.unpack('<29I',cam.mu.mem_read(cam.m()+f['state_fields']['canvas'],116)))
    assert native_canvas==canvas,(mode.mid,native_canvas,canvas)
    assert cam.get('canvas_valid')==1
    native_rate=cam.cstr(cam.w(cam.vars['SL_O_Rate']+8))
    assert native_rate==lib.slm_calc_rate().decode(),(mode.mid,native_rate,lib.slm_calc_rate())
    proof.append({'bin':[bh,bv],'ratio':ratio,'crop':[cw,ch],'output':got[:2],'lead':lead,'rate':native_rate})
    summary['cases']+=1
    if len(proof)==1:
     label=RL.NAMES+0x220;cam.mu.mem_write(label,b'VRC000\0')
     size=cam.call(cam.fn('rl_encode'),cam.m(),label,thumb=True,sp=V.T.STACK-0x1000)[0]
     if mode.depth==14:
      assert size==0,(mode.mid,size);summary['raw14_rejected']+=1
     else:
      assert size>0,(mode.mid,got,native_canvas)
      blob=bytes(cam.mu.mem_read(cam.block+f['export_off'],size))
      decoded=rcd.decode(blob,image=cam.img,stock_ids=set(cam.modes))
      assert decoded['act']==tuple(got[:2])
      assert decoded['modes'][0][0]==mode.mid
      summary['encoded']+=1
   if proof:summary['modes'][str(mode.mid)]=proof
   print('M%d: %d ARM cases'%(mode.mid,len(proof)),flush=True)
   pathlib.Path(report).write_text(json.dumps(summary,indent=2)+'\n')
   if limit is not None and summary['cases']>=limit:break
 assert not cam.misaligned,cam.misaligned
 summary.update(passed=True,seconds=round(time.monotonic()-start,3))
 pathlib.Path(report).write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k!='modes'},indent=2),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--report',required=True);parser.add_argument('--limit',type=int)
 args=parser.parse_args();run(args.report,args.limit)
