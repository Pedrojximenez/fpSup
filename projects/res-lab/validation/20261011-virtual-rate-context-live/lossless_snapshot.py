"""Bounded standby reads of the byte-pinned v0.2.0test Lossless module."""
import hashlib
import json
import pathlib
import sys
import camera as C
sys.path.insert(0,str(C.ROOT/'fpSup/lossless'))
import card_status

FIELDS = ('magic','menu.result','rec_events','rec_admitted','rec_raw','rec_menu_off',
          'rec_firmware_refused','hold_init_failed','hold_live','settings_on',
          'saves','save_failed','bulk','bulk_writer_open','take_frames',
          'hold.lane','hold.compressed','hold.held','hold.passed','hold.faults',
          'hold.not_eligible','hold.lanes_full','hold.stalls','hold.refused',
          'hold_b.lane','hold_b.compressed','hold_b.held','hold_b.faults',
          'rec.facts.seen.width','rec.facts.seen.height','rec.facts.seen.bits',
          'rec.facts.seen.raster','record_diag.raw_errors','record_diag.discard_count',
          'record_diag.lookup_missing','record_diag.completion_errors',
          'flush.applied','flush.trailer_failed','flush.length_mismatch')

def snapshot():
    assert C.recording()==0
    p=C.HERE/'sd-small-m12/lossless-layout'
    blob=(p/'10LOSS.BIN').read_bytes()
    assert hashlib.sha256(blob).hexdigest()=='ad984ce65a025d7acfbf968d0a7c3e43ef94bc89085af6b3a522374e7e9f8137'
    meta=json.loads((p/'build.json').read_text())['blob']
    fields=json.loads((p/'layout.json').read_text())['fields']
    record,state,base=card_status.find_record(C.live.putfile.mem_get)
    assert state==base+meta['state_off']
    start=meta['c_base'];end=start+meta['c_text']
    code=C.live.putfile.read_bulk(base+start,end-start,'tagged')
    assert code==blob[32+start:32+end]
    result={'record':hex(record),'state':hex(state),'base':hex(base),
            'code_sha256':hashlib.sha256(code).hexdigest(),
            'on_getter':C.value('MV_fpLossless'),
            'fields':{k:C.live.putfile.mem_get(state+fields[k],tries=1)[0] for k in FIELDS}}
    assert result['fields']['magic']==0x44524143 and result['fields']['menu.result']==1
    return result
