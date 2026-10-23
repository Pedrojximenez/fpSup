import fcntl,sys,time,snap
C=snap.C
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for k in sys.argv[1:]:
  if k.startswith('wait'):time.sleep(float(k[4:]));continue
  C.key(k);s=C.live.screen()
  print(k,s,C.value('MENU_Level1'),C.value('MENU_Level2') if s.startswith('B2') else '',flush=True)
