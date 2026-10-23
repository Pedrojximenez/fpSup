import fcntl,json,sys
from common import *
import camera as C
C.live.LOG=HERE/'commands.jsonl'
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 dest=HERE/(sys.argv[1]+'.json');assert not dest.exists()
 r=C.snapshot();dest.write_text(json.dumps(r,indent=1))
 print('screen',r['screen'],'fps',r['frame_rate_getter'],'quality',r['quality_getter'])
 print({k:r['state'][k] for k in ('FLAG','CUR','SEL','BITLATCH','PICKOK')})
 for row in r['rows']:print(row['index'],row['label'],'STOCK',row['STOCK'],'BITMASK',row['BITMASK'],'ON',row['ON'],row['AW'],row['AH'])
 print('picked',r.get('picked_entry',{}).get('key'))
