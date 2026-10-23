"""Read-only host SSD analysis of new clips, after the user confirms reconnection."""
from pathlib import Path
from collections import Counter
import hashlib,json,shutil,sys,tempfile,wave
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'projects/open-gate/build'))
from fpcam import parse_dng

def main():
 assert sys.argv[1:]==['after-confirmed-reconnect']
 before=json.loads((HERE/'ssd-host-before.json').read_text())['volumes']
 dest=HERE/'ssd-host-evidence';dest.mkdir()
 reports=[]
 for v in before:
  root=Path(v['volume'])/'CINEMA';assert root.is_dir(),root
  old={x['name'] for x in v['clips']}
  folders=sorted(p for p in root.iterdir() if p.is_dir() and p.name not in old)
  for folder in folders:
   local=dest/folder.name;local.mkdir()
   dngs=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.upper()=='.DNG');assert dngs
   report={'clip':folder.name,'source':str(folder),'count':len(dngs),'numbers':[int(p.stem.rsplit('_',1)[1]) for p in dngs],'files':[],'samples':[],'extras':[]}
   for p in dngs:
    data=p.read_bytes();offset=data.find(b'II*\0',0,0x20000)
    report['files'].append({'file':p.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'tiff_offset':offset})
   report['numbers_contiguous']=report['numbers']==list(range(1,len(dngs)+1));report['tiff_offsets']=dict(Counter(x['tiff_offset'] for x in report['files']))
   for i in sorted({0,(len(dngs)-1)//2,len(dngs)-1}):
    p=dngs[i];q=local/p.name;shutil.copyfile(p,q);data=q.read_bytes();offset=report['files'][i]['tiff_offset']
    if offset==0:main,ifds=parse_dng(q)
    elif offset>0:
     with tempfile.NamedTemporaryFile(suffix='.DNG') as tmp:
      tmp.write(data[offset:]);tmp.flush();main,ifds=parse_dng(tmp.name)
    else:main,ifds={'error':'No TIFF prefix within first128KiB'},[]
    sample={'file':q.name,'main_ifd':main,'ifds':ifds,'tiff_offset':offset,'relative_tag_parse_only':offset!=0}
    if offset==0:
     import rawpy
     try:
      with rawpy.imread(str(q)) as raw:sample['raw_shape']=list(raw.raw_image.shape)
     except Exception as e:sample['decode_error']=str(e)
    report['samples'].append(sample)
   for p in folder.iterdir():
    if not p.is_file() or p.suffix.upper() not in ('.WAV','.XMP','.TXT'):continue
    q=local/p.name;shutil.copyfile(p,q);extra={'file':q.name,'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()}
    if q.suffix.upper()=='.WAV':
     with wave.open(str(q)) as audio:extra.update(seconds=audio.getnframes()/audio.getframerate(),rate=audio.getframerate(),channels=audio.getnchannels())
    report['extras'].append(extra)
   reports.append(report)
   (dest/'manifest.json').write_text(json.dumps({'source_files_modified':False,'takes':reports,'limitations':'Manual actions and connection timing require user report. Tags and count/audio are not exact exposure-cadence or preview/FOV proof.'},indent=2)+'\n')
   print(folder.name,report['count'],report['tiff_offsets'],[(s['main_ifd'].get('FrameRate'),s.get('raw_shape')) for s in report['samples']],flush=True)
 assert reports,'No new SSD clip folders; do not infer a trial occurred'
if __name__=='__main__':main()
