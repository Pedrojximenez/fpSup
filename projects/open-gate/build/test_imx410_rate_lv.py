#!/usr/bin/env python3
"""Offline LV resource, capacity and original curve/drawText checks."""
import struct
import unittest
import imx410_rate_lv as L
IMAGE=(L.ROOT/'out/MAIN_c0000000.bin').read_bytes()
POOL=IMAGE[L.POOL_START-L.BASE:L.POOL_START-L.BASE+L.POOL_SIZE]
def rows(image,s):return L.N.split(image[s['start']-L.BASE:s['end']-L.BASE])
def header(rs):return L.A.parse_header(L.A.Record(0,rs[0].to_bytes()),lambda p:L.N.string_at(POOL,p))

class RateLV(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.words=L.patches(IMAGE);im=bytearray(IMAGE)
  for a,v,_ in cls.words:struct.pack_into('<I',im,a-L.BASE,v)
  cls.image=bytes(im)
 def test_four_sets_local_patch_runs(self):
  self.assertEqual(len(L.SETS),4);self.assertEqual(len(self.words),437)
  self.assertEqual(sum(i==0 or a!=self.words[i-1][0]+4 for i,(a,_,_) in enumerate(self.words)),52)
  self.assertEqual(len({a for a,_,_ in self.words}),len(self.words))
  self.assertTrue(all(any(s['start']<=a<s['end'] for s in L.SET_SPANS) for a,_,_ in self.words))
 def test_neighbors_and_set_boundaries(self):
  cursor=0
  for s in L.SETS:
   lo,hi=s['start']-L.BASE,s['end']-L.BASE
   self.assertEqual(self.image[cursor:lo],IMAGE[cursor:lo])
   old,new=rows(IMAGE,s),rows(self.image,s)
   self.assertEqual(sum(r.size for r in new),hi-lo)
   # Only the clip after the larger drawText moves; every later record
   # retains its original address, so no tail-wide patch is necessary.
   for a,b in zip(old,new):
    if s['start']+a.offset!=s['clip']:self.assertEqual(a.offset,b.offset)
   self.assertEqual(self.image[hi-8:hi],IMAGE[hi-8:hi]);cursor=hi
  self.assertEqual(self.image[cursor:],IMAGE[cursor:])
 def test_stock_pins_fail_closed(self):
  for s in L.SETS:
   im=bytearray(IMAGE);im[s['draw']-L.BASE-1]^=1
   with self.assertRaisesRegex(ValueError,'pinned stock'):L.rebuild(im,s)
 def test_header_budgets_and_object_identity(self):
  for s in L.SETS:
   old,new=rows(IMAGE,s),rows(self.image,s);a,b=header(old),header(new)
   self.assertEqual(len(old),len(new))
   self.assertEqual([r.to_bytes() for r in old if r.tag==0x10003],[r.to_bytes() for r in new if r.tag==0x10003])
   for k in ('objects','special_objects','groups','clip_property_counts','trailing_budget'):self.assertEqual(a[k],b[k])
   for k in a['component_counts']:
    delta=-1 if k=='drawImage' else 1 if k=='drawText' else 0
    self.assertEqual(a['component_counts'][k]+delta,b['component_counts'][k])
   self.assertEqual([11 if n==10 else n for n in a['property_key_counts']],b['property_key_counts'])
   def properties(rs):return [p for r in rs if r.tag==0x1000A for p in L._parse_clip(r,lambda p:L.N.string_at(POOL,p))['properties']]
   self.assertEqual(len(properties(old)),len(properties(new)))
   self.assertGreaterEqual(sum(b['property_key_counts']),sum(len(p['keys']) for p in properties(new)))
 def test_original_rate_order_and_hidden_15(self):
  for s in L.SETS:
   old=next(r for r in rows(IMAGE,s) if r.tag==0x1000A and r.words(5)[3:5]==(s['owner'],4))
   p=L.A.parse_clip(L.A.Record(0,old.to_bytes()),lambda p:L.N.string_at(POOL,p))['properties'][0]
   self.assertEqual([L.N.string_at(POOL,k['value']).split('_fps_')[1] for k in p['keys']],['1','24','2','3','48','4','5','6','7','15'])
  result=L.verify_installed(dict((a,v) for a,v,_ in self.words),base_image=IMAGE)
  self.assertEqual([(r['row9'],r['row10']) for r in result],[('240','15')]*4)
 def test_literal_donor_font_and_box(self):
  for s in L.SETS:
   r=next(r for r in rows(self.image,s) if r.tag==0x10005 and r.words(4)[3]==s['owner'])
   self.assertEqual(r.words(6),(0x2541C,32,0xFFFFFFFF,s['owner'],3,0x40002015));self.assertEqual(r.body[28],0)
   self.assertEqual(struct.unpack_from('>3I',r.body,29),(s['font_size'],0,0xFFFFFFFF))
   self.assertEqual(struct.unpack_from('>4f',r.body,41),(0,0,s['width'],s['height']))
 def test_native_header_is_arena_capacity_only(self):
  import nbu_probe as P
  for s in L.SETS:
   allocated=[]
   for image in (IMAGE,self.image):
    p=P.NbuProbe(image[:P.SEG0_SIZE]);p.install_arena()
    # Equal class-size stand-in isolates key-budget arithmetic. Transferring
    # one drawable keeps total component count, so this term cancels.
    p.stub(0xC05D9E88,'class-size allocation arithmetic',ret=0)
    raw=rows(image,s)[0].to_bytes();p.open(blob=raw,magic=False,cursor=0,pool=(L.POOL_SIZE,L.POOL_START),owner=True)
    t=p.record();self.assertEqual(t.consumed,len(raw))
    allocated.append([c.args[1] for c in t.calls if c.address==0xC05E8EF8])
   self.assertEqual(len(allocated[0]),1);self.assertEqual(allocated[1][0]-allocated[0][0],s['key_budgets']*56)
 def test_native_installed_parser_curve_and_setter(self):
  result=L.verify_installed(self.image,native=True);self.assertEqual(len(result),4)
  for r in result:
   self.assertTrue(r['native_interpreter_executed']);self.assertFalse(r['gui_rendered'])
   states=dict(r['native_curve_text_states'])
   self.assertEqual((states[300],states[333],states[316],states[334]),('240','15','240','15'))
 def test_native_clip_padding_is_skipped_not_interpreted(self):
  for spec in L.SETS:
   clip=next(r for r in rows(self.image,spec) if r.tag==0x1000A and r.words(5)[3:5]==(spec['owner'],4))
   data=clip.to_bytes();semantic=len(data)-spec['shrink']
   result=L._verify_native_clip(self.image,data,semantic)
   self.assertEqual(result['labels'],list(L.LABELS));self.assertEqual(result['times'],list(L.TIMES))
   poison=data[:semantic]+bytes([0xA5])*spec['shrink']
   self.assertEqual(L._verify_native_clip(self.image,poison,semantic),result)
   self.assertEqual(result['skip'],[(semantic,spec['shrink'])])
 def test_native_curve_rejects_wrong_240_key(self):
  import nbu_probe as P
  keys=[dict(time=t,value=v) for t,v in zip(L.TIMES,L.LABEL_OFFSETS)];keys[9]['value']=L.LABEL_OFFSETS[10]
  with self.assertRaisesRegex(ValueError,'wrong frame-rate key'):L._verify_native_curve_and_text(P.NbuProbe(IMAGE[:P.SEG0_SIZE]),keys)

if __name__=='__main__':unittest.main(verbosity=2)
