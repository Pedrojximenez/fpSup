"""Poison real ARM producer fields; reject before touching active consumer data."""
import json,pathlib,struct,time
import test_virtual_rcd as V

def run(report):
    started=time.monotonic();out,f=V.built()
    test=V.VirtualTests('test_contract_abi_and_status');test.out,test.f=out,f
    cam=test.boot();cam.geometry();assert cam.apply()==0
    active=cam.snapshot();generation=cam.w(cam.service()+16);cam.lv.clear()
    fields=dict(f['state_fields'])
    # sl_menu.h places the two uint32 standby fields immediately after axis_armed.
    assert fields['mode_ids']==fields['axis_armed']+12
    fields.update(sb_vis_w=fields['axis_armed']+4,sb_vis_h=fields['axis_armed']+8)
    size=fields['export_text']+64
    original=bytes(cam.mu.mem_read(cam.m(),size))
    cases=[('record width', 'canvas', 0, 16),
           ('record height', 'canvas', 1, 2),
           ('preview width past source', 'canvas', 2, 4096),
           ('preview height past source', 'canvas', 3, 4096),
           ('empty preview', 'canvas', 5, 0),
           ('record crop mismatch', 'canvas', 6, 2992),
           ('preview bin', 'canvas', 10, 2),
           ('record bin mismatch', 'canvas', 11, 1),
           ('preview zoom too large', 'canvas', 12, 16385),
           ('record zoom too large', 'canvas', 13, 16385),
           ('movie class', 'canvas', 14, 1),
           ('producer preview mismatch', 'canvas', 21, 16),
           ('producer record mismatch', 'canvas', 24, 2),
           ('raw width mismatch', 'canvas', 25, 1),
           ('zero standby width', 'sb_vis_w', None, 0),
           ('standby height past maximum', 'sb_vis_h', None, 1335),
           ('crop removes whole window', 'crop_w', None, 3032),
           ('unsupported bin', 'bin_h', None, 5),
           ('forged mode raster', 'ro_w', None, 3048),
           ('forged mode scale', 'ro_sx', None, 1)]
    proof=[]
    for name,field,index,value in cases:
        cam.mu.mem_write(cam.m(),original)
        at=cam.m()+fields[field]+(4*index if index is not None else 0)
        cam.put(at,value)
        label=V.T.STACK-0x9000;cam.mu.mem_write(label,b'VRC000\0')
        assert cam.call(cam.fn('rl_encode'),cam.m(),label,thumb=True,sp=V.T.STACK-0x1000)[0]==0,name
        assert cam.apply()==5,name
        assert cam.snapshot()==active,name
        assert cam.w(cam.service()+16)==generation,name
        assert not cam.lv,name
        cam.assert_tables(test)
        proof.append(name)
    cam.mu.mem_write(cam.m(),original)
    assert cam.apply()==0
    assert cam.w(cam.service()+16)==generation+1
    assert not cam.misaligned
    result={'card':str(out),'module_sha256':json.loads((out/'build.json').read_text())['sha256'],
            'rejections':proof,'cases':len(proof),'active_recipe_preserved':True,
            'valid_after_poisoning':True,'passed':True,'seconds':round(time.monotonic()-started,3)}
    pathlib.Path(report).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--report',required=True)
    run(p.parse_args().report)
