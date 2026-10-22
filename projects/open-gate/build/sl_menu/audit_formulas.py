"""Enumerate real firmware modes against independent geometry invariants.

This executes the production C calculator on the host, without USB. It checks
physical bounds instead of treating another copy of the same formulas as truth.
"""
import argparse,collections,ctypes as ct,json,pathlib,tempfile,time
import test_sl_modes as T

BIN={0:1,1:3,2:5}

def audit(report, replace=None):
 started=time.monotonic();issues=collections.Counter();examples=[];example_counts=collections.Counter();modes={};tested=0
 with tempfile.TemporaryDirectory(prefix='reslab-formula-audit-') as tmp:
  lib=T.build(tmp,replace=replace,calc_only=True)
  lib.slm_calc_seed.argtypes=[ct.c_uint32]*12
  lib.slm_calc_get.argtypes=[ct.c_uint32];lib.slm_calc_get.restype=ct.c_uint32
  lib.slm_calc_rate.argtypes=[];lib.slm_calc_rate.restype=ct.c_char_p
  fixture=T.Modes();fixture.camera(lib,rec_cap=(0,0))
  lib.slm_pages(0x56000000,0x57000000,123);lib.slm_ui(1)
  for mode in T.REG.modes:
   w,h=mode.raw;sx,sy=mode.scale
   crops=[(0,0),((w//2)&~15,(h//2)&~1),((w-64)&~15,0),(0,(h-64)&~1),((w-64)&~15,(h-64)&~1)]
   counts=collections.Counter();ncase=0
   for bh,bv in ((1,1),(3,1),(1,3),(3,3)):
    for ratio in range(17):
     for cw,ch in crops:
      for ow,oh in ((w,h),(16,2),((w//2)&~15,(h//2)&~1)):
       for lead in (0,1):
        ncase+=1;tested+=1
        lib.slm_calc_seed(mode.mid,w,h,sx,sy,bh,bv,cw,ch,ratio,ow,oh)
        lib.slm_clear_posts();lib.slm_fit(lead)
        result=[lib.slm_calc_get(i) for i in range(12)]
        canvas=[lib.slm_calc_get(32+i) for i in range(29)]
        aw,ah,bh_,bv_,cw_,ch_=result[:6]
        bad=[]
        if not aw or not ah or aw%16 or ah%2:bad.append('output_alignment')
        if cw_>=w or ch_>=h:bad.append('crop_outside_readout')
        if aw+16>((w-cw_)//bh_&~15):bad.append('width_exceeds_cut_readout')
        if ah+10>((h-ch_)//bv_&~1):bad.append('height_exceeds_cut_readout')
        if result[11]:
         if any(z<1023 or z>16384 for z in (canvas[12],canvas[13],canvas[19],canvas[20])):bad.append('zoom_outside_planner_domain')
         if canvas[0]<aw+16 or canvas[1]<ah+10:bad.append('record_cannot_hold_visible_crop')
         if canvas[0]>(w//bh_&~15) or canvas[1]>(h//bv_&~1):bad.append('record_exceeds_source')
         ph=BIN.get(canvas[10],0)*max(canvas[12],1024)
         pv=BIN.get(canvas[17],0)*max(canvas[19],1024)
         if not ph or not pv:bad.append('invalid_preview_path')
         else:
          sw=w*1024//ph;sh=h*1024//pv
          if canvas[2]>sw or canvas[3]>sh:bad.append('preview_raster_exceeds_source')
         if not canvas[5] or not canvas[7]:bad.append('empty_preview')
         if not result[7] or not result[8] or result[7]>2000 or result[8]>1334:bad.append('invalid_standby_size')
         bits=14 if mode.depth==14 else 12
         expected_mb=(canvas[0]*canvas[1]*bits*2398+400000000)//800000000
         if lib.slm_calc_rate().decode()!=f'23.98p {expected_mb} MB/s':bad.append('data_rate_does_not_match_record_matrix')
        else:bad.append('no_canvas_for_fitted_geometry')
        lib.slm_clear_posts();lib.slm_fit(lead)
        again=[lib.slm_calc_get(i) for i in range(12)]
        if result!=again:bad.append('fit_not_idempotent')
        for kind in bad:issues[kind]+=1;counts[kind]+=1
        if bad and any(example_counts[kind]<12 for kind in bad):
         examples.append({'mode':mode.mid,'raw':[w,h],'scale':[sx,sy],'bin':[bh,bv],
          'ratio':ratio,'crop_requested':[cw,ch],'output_requested':[ow,oh],'lead':lead,
          'result':result,'canvas':canvas,'errors':bad})
         example_counts.update(bad)
   modes[str(mode.mid)]={'cases':ncase,'issues':dict(counts)}
   print('M%d: %d cases, %d issues'%(mode.mid,ncase,sum(counts.values())),flush=True)
 data={'mode_count':len(modes),'cases':tested,'issues':dict(issues),'examples':examples,
       'modes':modes,'seconds':round(time.monotonic()-started,3),'passed':not issues}
 pathlib.Path(report).write_text(json.dumps(data,indent=2)+'\n')
 print(json.dumps({k:v for k,v in data.items() if k not in ('examples','modes')},indent=2),flush=True)
 return data

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report',required=True)
 a=p.parse_args();r=audit(a.report);raise SystemExit(0 if r['passed'] else 1)
