"""Validate the real audit comparison without importing any live camera code."""
import ast,hashlib,json,pathlib,struct,sys
ROOT=pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L
import rcd
live=ROOT/'projects/res-lab/validation/20261009-oncamera'
source=ast.parse((live/'final_audit.py').read_text())
node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='verify_bytes')
env={'L':L,'rcd':rcd,'struct':struct,'hashlib':hashlib,
     'proof':json.loads((live/'v6-complete-audit.json').read_text())}
exec(compile(ast.Module(body=[node],type_ignores=[]),'final_audit.py','exec'),env)
check=env['verify_bytes'];remote='\\fpSup\\32RESCUS.BIN'
actual=(live/'v6-complete-readback/32RESCUS.BIN').read_bytes()
expected=(ROOT/'projects/res-lab/cards/20261009-virtual-rcd-v6/debug/fpSup/32RESCUS.BIN').read_bytes()
assert check(remote,actual,expected)['settings']['checksum_valid']
mutations={}
for label,offset,rehash in [('program changed',256,False),('bad checksum',108,False),
                             ('enabled formats changed',56,True),('wrong selected label',44,True)]:
    blob=bytearray(actual);blob[offset]^=1
    if rehash:struct.pack_into('<I',blob,32+L.CFG['SUM'],rcd.fnv(blob[32:32+L.CFG['SUM']]))
    try:check(remote,bytes(blob),expected)
    except AssertionError:mutations[label]=True
    else:raise AssertionError('Undetected mutation: '+label)
result={'valid_saved_settings_accepted':True,'mutations_rejected':mutations,'passed':True}
pathlib.Path(__file__).with_name('audit-settings-tests.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
