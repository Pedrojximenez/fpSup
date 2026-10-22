"""Read known-size trial DNG samples only after fresh HDMI and native standby."""
import fcntl, hashlib, importlib, json, pathlib, re, subprocess, sys
import numpy as np
from PIL import Image
import camera as C
sys.path.insert(0,str(C.HERE))
from record_trial import overlay
sys.path.insert(0,str(C.ROOT/'projects/open-gate/build'))
from fpcam import parse_dng

def main():
    labels=sys.argv[1:]
    assert labels and all(x in ('tagged-120-quiet','tagged-240-quiet','tagged-280-quiet',
        'tagged-280-inner-v13-quiet','tagged-280-inner-v14-quiet',
        'tagged-240-inner-v14-quiet','tagged-120-inner-v14-quiet',
        'tagged-240-sensorlab-v15-quiet','tagged-280-sensorlab-v15-quiet',
        'h2-native30-v16-quiet','tagged-h2-cpu-header-v17-quiet',
        'tagged-240-small-lossless-v17-quiet','sensor-only-native30-quiet20') for x in labels)
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert C.recording()==0 and C.live.screen()=='LV_CINE_MEDIUM'
        resume = labels == ['sensor-only-native30-quiet20']
        proof=C.HERE/('before-dng-read-'+labels[0]+('-resume' if resume else '')+'.png')
        assert not proof.exists()
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','avfoundation','-framerate','30','-pixel_format','uyvy422','-i','AVerMedia ExtremeCap UVC:none','-vf','scale=1024:576','-frames:v','1',str(proof)],check=True,timeout=15)
        assert overlay(np.asarray(Image.open(proof).convert('RGB')))['standby_visible']
        assert C.recording()==0 and 'slot = sd0' in C.live.checked_sh('sdcard slot')
        getter=importlib.import_module('getfile')
        getter.read_direct=lambda addr,size:C.live.putfile.read_bulk(addr,size,'tagged')
        for label in labels:
            dest=C.HERE/label;t=json.loads((dest/'trial.json').read_text())
            assert t['phase']=='captured' and t['standby_after'] and len(t['new_clips'])==1
            clip=t['new_clips'][0];date=t['clips_after'][clip]
            # This take crossed midnight: directory date12, actual filename11.
            # The first file was successfully read with that exact name after
            # native open returned0 for the directory-date filename.
            if resume:
                assert clip=='A001_089' and date=='20261012'
                date='20261011'
            size=int(re.search(r'file-size=(\d+),',t['record_log'])[1])
            req,count=map(int,re.search(r'req_cnt=(\d+), fin_cnt=(\d+),',t['record_log']).groups())
            expected_size=507904 if label=='tagged-240-small-lossless-v17-quiet' else 1095168
            assert 0<req==count<=2000 and size==expected_size
            report=dest/'raw-frames.json';assert not report.exists()
            result={'clip':clip,'size':size,'requested':req,'finished':count,'filename_date':date,'transport':'source-address tagged read_bulk','standby_proof':str(proof),'sampling':'first/middle/last, not full sequence','frames':[]}
            for n in sorted({1,(count+1)//2,count}):
                assert C.recording()==0
                local=dest/f'{clip}-{n:06d}.DNG'
                remote=f'\\CINEMA\\{clip}\\{clip}_{date}_{n:06d}.DNG'
                if resume and n==1:
                    assert local.is_file() and local.stat().st_size==size
                else:
                    assert not local.exists()
                    sys.argv=['getfile.py',remote,str(local),'--size',str(size)]
                    rc=getter.main();assert rc==0
                data=local.read_bytes();assert len(data)==size
                main_ifd,ifds=parse_dng(local)
                result['frames'].append({'number':n,'path':str(local),'sha256':hashlib.sha256(data).hexdigest(),'main_ifd':main_ifd,'ifds':ifds})
                report.write_text(json.dumps(result,indent=2)+'\n')
            print(label,[(f['number'],f['sha256']) for f in result['frames']],flush=True)
if __name__=='__main__':main()
