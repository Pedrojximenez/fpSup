"""Bounded quiet trial of the reconstructed H2 static RCD, native30 carrier.

Shares the existing runner's HDMI, native standby, single-pulse and no-poll
guards. This verifies the actual owned sensor clone before/after capture,
without applying a RES-Lab recipe or invoking a private selector.
"""
import json
import struct
import sys
import camera as C
from ogc_layout import S, VM, VM_BUF
sys.path.insert(0,str(C.HERE))
import record_trial
assert record_trial.__file__==str(C.HERE/'record_trial.py')


def check(r,quality):
    assert quality==0 and r['quality_getter'].strip()=='0'
    assert r['registry']['lock']==0 and r['registry']['provider']==0
    assert r['producer']['applied_valid']==0
    assert r['consumer']['flag']==1 and r['consumer']['current']>0
    row=r['rows'][r['consumer']['current']-1]
    assert [row[k] for k in ('label','width','height','on')]==['H2S240',992,662,1]
    assert r['fps_state']['VRATE']==0 and r['picked_entry']['VRATE']==0
    assert r['fps_getter'].strip()=='3' and C.value('MV_FrameRate')==3
    manifest=json.loads((C.HERE/'h2-success-rcd/manifest.json').read_text())
    e=r['picked_entry'];want=manifest['tested_entry']
    assert (e['W0'],e['W1'],e['ENGFPS'],e['NOMINAL'])==tuple(want[k] for k in ('w0','w1','engfps','nominal'))
    assert r['engine_fps']==struct.unpack('<f',struct.pack('<I',want['engfps']))[0]
    assert abs(r['sensor_timing_fps']-manifest['sensor_fps'])<.001
    s=int(r['consumer_state'],16)
    block=C.inspect.FACT['rescustom']['block']
    vms=C.live.putfile.mem_get(s+S['VMS'],tries=1)[0]
    count=C.live.putfile.mem_get(s+S['NVM'],tries=1)[0]
    core=int(r['consumer_base'],16)
    assert 0<count<=16 and 0<=e['VM']<count and 0<vms and s+vms+count*VM['SIZE']<=core+block
    vm=s+vms+e['VM']*VM['SIZE']
    words=C.live.putfile.mem_get(vm,16,tries=1)
    assert words[VM['ID']//4]==e['MODE']
    assert words[VM['DONOR']//4]==12 and words[VM['FILLED']//4]==1
    assert [words[VM[k]//4] for k in ('TW0','TW1','NOM')]==[want['w0'],want['w1'],240]
    tim=words[VM['PTR']//4]
    # The filled TIM row must lie inside this exact consumer-owned VM buffer.
    assert vm+VM_BUF['TIM']<=tim and tim+32<=vm+VM_BUF['TIM']+32+32
    actual=C.live.putfile.mem_get(tim,8,tries=1)
    assert actual[1:3]==[want['w0'],want['w1']]
    assert r['sensorlab_profile']['M12_LEGACY_HITS']==0
    assert r['header_copy']['HDR_COPY_HITS']==0 and r['header_copy']['BULK_HITS']==0
    return {'label':'H2S240','native_carrier':'30000/1001','physical_sensor_fps':72000000/((actual[1]&65535)*((actual[2]&65535)-1)+(actual[1]>>16)),
            'engine_fps':r['engine_fps'],'vm_address':hex(vm),'vm_words':words,
            'tim_address':hex(tim),'actual_tim_words':actual,
            'original_header_and_bulk_path':True,
            'limitation':'Timing table readback verifies applied configuration, not measured exposure cadence.'}


if __name__=='__main__':
    assert len(sys.argv)==2
    sys.argv=[sys.argv[0],sys.argv[1],'2997','0','quiet']
    record_trial.main(historical_check=check)
