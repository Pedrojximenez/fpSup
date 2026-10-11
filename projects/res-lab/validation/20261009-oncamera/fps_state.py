"""Read-only frame-rate proof; never invoke a private picker or FPS callback."""
import fcntl,json,pathlib,struct,sys
import live_camera as live
import inspect_runtime as inspect
sys.path.insert(0,str(live.ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L

def snapshot():
    r=inspect.snapshot();s=int(r['consumer_state'],16)
    r['fps_state']={k:live.putfile.mem_get(s+L.S[k])[0]
                    for k in ('VR_UI','VR_WHY','VRATE','VR_COMMITS','DIRTY','PICKOK','FPSLATCH','LAST_ENT','HITS')}
    r['engine_state_valid']=bool(r['consumer']['flag'] and r['consumer']['current'])
    if r['engine_state_valid']:
        r['engine_fps']=struct.unpack('<f',struct.pack('<I',r['fps_state']['FPSLATCH']))[0]
    off=r['fps_state']['LAST_ENT']
    if off and r['engine_state_valid']:
        start=live.putfile.mem_get(s+L.S['ENTS'])[0]
        count=live.putfile.mem_get(s+L.S['NENT'])[0]
        assert start<=off<start+count*L.ENT['SIZE'] and (off-start)%L.ENT['SIZE']==0
        words=live.putfile.mem_get(s+off,L.ENT['SIZE']//4)
        r['picked_entry']={k:words[v//4] for k,v in L.ENT.items() if k not in ('SIZE','KEY')}
        w0,w1=r['picked_entry']['W0'],r['picked_entry']['W1']
        r['frame_cycles']=(w0&0xffff)*((w1&0xffff)-1)+(w0>>16)
        r['sensor_timing_fps']=72000000/r['frame_cycles']
    r['fps_gui']={k:live.checked_sh('gui geti '+k) for k in ('MV_FrameRate','EXCL_FrameRate')}
    r['fps_getter']=live.checked_sh('menu SetMovFramerate')
    r['quality_getter']=live.checked_sh('menu SetMovCinemaDNGQuality')
    r['screen']=live.screen()
    return r

if __name__=='__main__':
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        r=snapshot();dest=pathlib.Path(__file__).with_name('fps-'+sys.argv[1]+'.json')
        assert not dest.exists(),dest
        dest.write_text(json.dumps(r,indent=2)+'\n')
        if len(sys.argv)>2:assert r['fps_state']['VRATE']==int(sys.argv[2]),r['fps_state']
        print(json.dumps({k:r[k] for k in ('fps_state','fps_gui','fps_getter','quality_getter','screen','engine_fps','picked_entry','frame_cycles','sensor_timing_fps') if k in r},indent=2))
