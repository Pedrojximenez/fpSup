"""Select a native FPS popup row using its actual cursor variable."""
import fcntl,pathlib,re,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'projects/res-lab/validation/20261009-oncamera'))
import live_camera as L
def value(name):
 s=L.checked_sh('gui geti '+name);m=re.fullmatch(r'\s*OK:'+name+r' -> (-?\d+)\s*',s);assert m,s
 return int(m[1])
def key(name):
 L.checked_sh('key '+name+'ON');time.sleep(.12);L.checked_sh('key '+name+'OFF');time.sleep(.8)
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert 'is_recording -> 0' in L.checked_sh('status get is_recording')
 assert L.screen()=='B2_5' and value('MENU_Level2')==4434
 target=int(sys.argv[1]);assert 0<=target<=12
 key('RIGHT');cur=value('B2_n5_ListFocus4');assert 0<=cur<=12
 for _ in range(13):
  if cur==target:break
  want=cur+ (1 if cur<target else -1);key('DOWN' if cur<target else 'UP')
  cur=value('B2_n5_ListFocus4');assert cur==want,(cur,want)
 assert cur==target
 key('OK');assert value('MV_FrameRate')==target
 print('Committed native GUI FPS row',target,flush=True)
