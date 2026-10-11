"""Validate the full-height candidate readback, not image quality or recording success."""
import argparse,json,struct,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def analyze(folder):
    manifest=json.loads((ROOT/'diagnostics/three-k-f1/manifest.json').read_text())
    expected={'LOADED.BIN','STATUS.BIN',*[f'WORD{i}.BIN' for i in range(len(manifest['table_entries']))]}
    actual={p.name for p in folder.iterdir() if p.is_file() and p.suffix.upper()=='.BIN'}
    if actual!=expected:raise ValueError(f'Incomplete or ambiguous generation: {sorted(actual)}')
    loaded=(folder/'LOADED.BIN').read_bytes()
    if hashlib.sha256(loaded).hexdigest()!=manifest['payload_sha256']:raise ValueError('Loaded payload mismatch')
    status=(folder/'STATUS.BIN').read_bytes()
    if len(status)!=16:raise ValueError('Wrong status length')
    magic,code,address,value=struct.unpack('<4I',status)
    if magic!=0x3146334b:raise ValueError('Payload did not produce the expected status magic')
    words=[]
    for i,e in enumerate(manifest['table_entries']):
        data=(folder/f'WORD{i}.BIN').read_bytes()
        if len(data)!=4:raise ValueError(f'Wrong WORD{i} size')
        words.append(struct.unpack('<I',data)[0])
    target_matches=words==[e['replacement'] for e in manifest['table_entries']]
    applied=code==16 and target_matches
    if code==16 and not applied:raise ValueError('Success status contradicts table readbacks')
    return dict(applied=applied,status=code,mismatch_address=hex(address),mismatch_value=value,
                table_words=words,payload_exact=True,readbacks_match_target=target_matches,
                invocation_result=('applied_this_invocation' if applied else
                    'refused_stock_check_but_all_readbacks_already_match_target' if code==4 and target_matches else 'not_applied_this_invocation'),
                limitation='Does not prove a recording used the profile. Inspect the returned DNG. Requested full-height coverage still needs comparison with a same-position full-resolution still.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    report=analyze(a.folder);text=json.dumps(report,indent=2)+'\n'
    if a.output:a.output.write_text(text)
    print(text)
