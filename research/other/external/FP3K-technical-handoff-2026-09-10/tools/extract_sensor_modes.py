"""Extract verified table records; uncertain fields stay explicitly unnamed."""
from pathlib import Path
import struct,json
ROOT=Path(__file__).resolve().parents[1]
b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes();d=(ROOT/'analysis/firmware/DAT1_c2ef6e00.bin').read_bytes()
timing,n1,geometry,n2,pairs,n3=struct.unpack_from('<6I',d,0xc2f1e654-0xc2ef6e00)
assert (timing,n1,geometry,n2,pairs,n3)==(0xc0b59500,70,0xc0b59dc0,70,0xc0b5b918,70)
rows=[]
for i in range(n1):
 a=geometry-0xc0000000+i*100;v=struct.unpack_from('<25I',b,a);t=struct.unpack_from('<I14H',b,timing-0xc0000000+i*32);pair=struct.unpack_from('<2I',b,pairs-0xc0000000+i*8)
 assert v[0]==t[0]==pair[1]
 rows.append(dict(index=i,mode_id=v[0],geometry_address=0xc0000000+a,raster=[v[1],v[2]],output_crop=[v[11],v[12]],crop_origin=[v[13],v[14]],geometry_words=list(v),timing_record=list(t),mode_class=pair[0]))
(ROOT/'analysis/firmware/sensor-modes.json').write_text(json.dumps(rows,indent=2)+'\n')
s=['# Extracted sensor geometry','', 'Directly extracted from the supplied firmware. The DAT1 descriptor identifies 70 records; the accessor at 0xC0321028 uses 100-byte geometry records. Names of remaining fields and hardware sampling behavior are not assumed.','', '| Index | Mode ID | RAW raster | Output crop | Crop origin |','|---:|---:|---|---|---|']
for r in rows:s.append(f"| {r['index']} | {r['mode_id']} | {r['raster'][0]}×{r['raster'][1]} | {r['output_crop'][0]}×{r['output_crop'][1]} | {r['crop_origin']} |")
(ROOT/'analysis/firmware/sensor-modes.md').write_text('\n'.join(s)+'\n');print('Extracted 70 matching geometry/timing/mode-class records')
