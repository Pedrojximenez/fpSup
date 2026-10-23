"""Press keys (menu keys only), print screen + focus after each."""
import fcntl,sys,snap
C=snap.C
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for k in sys.argv[1:]:
  C.key(k);print(k,C.live.screen(),C.value('MENU_Level1'),flush=True)
