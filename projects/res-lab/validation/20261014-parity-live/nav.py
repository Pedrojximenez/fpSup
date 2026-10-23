"""Native menu helper: open Record Settings (B2_5) from live view, or set the frame-rate row and go back."""
import fcntl,sys,time
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]/'20261012-m12-240-live'))
from common import *
import camera as C
C.live=live
def to_b25():
 s=live.screen()
 if s=='LV_CINE_MEDIUM':C.key('MENU');s=live.screen()
 if s=='MainB1':C.key('RIGHT');s=live.screen()
 assert s=='MainB2',s
 cur=C.value('MENU_Level1')
 while cur!=650:C.key('DOWN');cur=C.value('MENU_Level1')
 C.key('RIGHT');time.sleep(1);assert live.screen()=='B2_5'
def set_rate(row):
 cur=C.value('MENU_Level2')
 while cur!=4434:
  assert cur in (4247,4297,4254),cur;C.key('DOWN');cur=C.value('MENU_Level2')
 C.key('RIGHT');cur=C.value('B2_n5_ListFocus4')
 while cur!=row:
  k='DOWN' if cur<row else 'UP';C.key(k);n=C.value('B2_n5_ListFocus4');assert n==cur+(1 if k=='DOWN' else -1),n;cur=n
 C.key('OK');assert C.value('MV_FrameRate')==row
def back():
 C.key('MENU')
 if live.screen()!='LV_CINE_MEDIUM':C.key('MENU')
 time.sleep(2);assert live.screen()=='LV_CINE_MEDIUM'
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 a=sys.argv[1:]
 if a[0]=='open':to_b25()
 elif a[0]=='rate':set_rate(int(a[1]));back()
 print('rate',C.value('MV_FrameRate'),live.screen())
