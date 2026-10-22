"""Quiet 20-second small M12 SD trial using the already released Lossless fix."""
import json
import struct
import sys
import camera as C
sys.path.insert(0,str(C.HERE))
import record_trial
import lossless_snapshot
assert record_trial.__file__==str(C.HERE/'record_trial.py')
assert lossless_snapshot.__file__==str(C.HERE/'lossless_snapshot.py')

rank=int(sys.argv[2]);assert rank in (23976,27972)

def check(r,quality):
    assert quality==0 and r['quality_getter'].strip()=='0'
    assert r['registry']['lock']==0 and r['registry']['provider']==0x42414c52
    p=r['producer']
    assert p['applied_valid']==1 and p['applied_geometry']==12
    assert [p[k] for k in ('out_w','out_h','bin_h','bin_v','crop_w','crop_h','lens_on','output_policy')]==[640,426,1,1,0,0,0,0]
    assert r['consumer']['flag']==1 and r['consumer']['current']==r['registry']['row']+1
    row=r['rows'][r['consumer']['current']-1]
    assert [row[k] for k in ('width','height','on')]==[640,426,1]
    assert r['fps_state']['VRATE']==rank and r['picked_entry']['VRATE']==rank
    fps=(240000 if rank==23976 else 280000)/1001
    assert r['engine_fps']==struct.unpack('<f',struct.pack('<f',fps))[0]
    assert abs(r['sensor_timing_fps']-fps)<.001
    loss=lossless_snapshot.snapshot()
    assert loss['on_getter']==1 and loss['fields']['settings_on']==1
    return {'geometry':[640,426],'rank':rank,'sensor_configuration_fps':r['sensor_timing_fps'],
            'engine_fps':r['engine_fps'],'lossless':loss,
            'limitation':'Timing readback verifies configuration; physical cadence and every DNG remain separate checks.'}

if __name__=='__main__':
    label=sys.argv[1]
    sys.argv=[sys.argv[0],label,str(rank),'0','quiet']
    record_trial.main(runtime_check=check,stop_after=20.0,frame_count=900)
