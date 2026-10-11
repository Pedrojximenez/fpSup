"""Collect verified candidate artifacts for the camera demo; no media writes."""
from pathlib import Path
import json,hashlib,shutil,zipfile

ROOT=Path(__file__).resolve().parents[1];P=ROOT/'prototype/fp3k-0.3.2-native-ui'
D=ROOT/'prototype/development';manifest=json.loads((P/'manifest.json').read_text())
sha=manifest['files']['FP3KMENU.BIN']['sha256']
verification=json.loads((P/'package-verification.json').read_text())
assert verification['files']==manifest['files'] and len(verification['cases'])==13 and all(c['passed'] for c in verification['cases'])
payload=(P/'FP3KMENU.BIN').read_bytes()
symbols=manifest['resident']['symbols'];base=int(manifest['resident']['base'],16)
pack=payload[int(symbols['ui_pack'],16)-base:int(symbols['ui_pack_end'],16)-base]
assert pack==(D/'native-ui/FP3KUI.NBR').read_bytes()
pack_sha=hashlib.sha256(pack).hexdigest()
assert json.loads((D/'native-ui/resource-pack-verification.json').read_text())['pack_sha256']==pack_sha
badge_index=json.loads((D/'native-ui/badges.json').read_text())
assert badge_index['pack_sha256']==pack_sha
badge_tests=json.loads((D/'native-ui/badge-verification.json').read_text())
assert {x['asset']:x['sha256'] for x in badge_tests['cases']}=={x['name']+'.xci':x['sha256'] for x in badge_index['assets']}
manifest['status']='Offline checks passed; ready for camera UI demo'
manifest['ui_pack_sha256']=pack_sha
(P/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for source,count in [(D/'native-menu/resident-verification.json',113),
                     (D/'native-ui/layout-ui-verification.json',400),
                     (D/'native-ui/layout-animation-verification.json',328)]:
    report=json.loads(source.read_text())
    assert report['payload_sha256']==sha and len(report['cases'])==count and all(c['passed'] for c in report['cases'])
    shutil.copy2(source,P/source.name)
for name in ['badge-verification.json','resource-pack-verification.json','badges.json']:
    shutil.copy2(D/'native-ui'/name,P/name)
for name in ['csv-verification.json','label-verification.json','range-verification.json']:
    shutil.copy2(D/'native-menu'/name,P/name)
for label in ['SD','SSD']:(ROOT/'diagnostics/native-ui-qs-return'/label/'FP3KM2').mkdir(parents=True,exist_ok=True)
(ROOT/'diagnostics/native-ui-qs-return/clips').mkdir(parents=True,exist_ok=True)
(P/'README.md').write_text('''# FP3K 0.3.2 — native UI candidate

For the Sigma fp running firmware 5.02. This RAM patch retains the existing
3000×2000 capture prototype and adds native 3K display assets, HUD publishers,
and QS selection handling. Version 0.3.2 repairs the independent settings
summary text, extends complete animation states and companion layout tracks,
and publishes HUD changes even when its observer predates AutoRun. It also
adds the large QS resolution badge, unhides the third footer choice only for
resolution, and redirects its cursor to the stock three-choice animation. The new UI integration has passed offline checks;
its appearance and startup behavior still need the camera demo. Cached screen
instances and final renderer behavior remain unverified. The 0.3 camera test
failed visually despite passing its earlier offline checks. The 0.3.1 camera
test confirmed the HUD, but summary and QS still failed. This candidate corrects
the previously misidentified summary row and omitted QS layers.

The main resolution list says **3K 3000x2000**. The intended HUD and QS badge
is **3K**. There is no timed startup wait and no drawn-on-top status overlay.

## Camera demo

1. With the camera off, remove its battery for 30 seconds once after installing
   this version. Reinsert it and connect the SD and SSD to the camera.
2. Use CINE, CinemaDNG, 12-bit, true 24 fps, crop off, recording to SSD. Set these
   before selecting 3K; changing recording settings deselects the private mode.
3. Select **3K 3000x2000** in the main resolution list. Check the live HUD and QS
   show **3K**. No timed loading message or extra startup action is required.
4. Open QS and inspect the resolution tile and surrounding tiles. Switch
   to UHD, then back to 3K, and check the HUD and settings summary each time.
5. No recording is needed for this UI check; the returned recordings already
   established both 3000x2000 and restored UHD output at 12-bit/24 fps.
6. Wait for media activity to finish, power off, and reconnect both media to the
   computer. Report which labels/choices appeared; no photograph is required.

Return folders are already created under `diagnostics/native-ui-qs-return`.
Startup diagnostic files remain in `FP3KM2` on the media.

## Current limits

The live preview remains 16:9/cropped. This update does not change preview
readout or framing. 25/30 fps and other recording formats are not supported by
this prototype. All-photosite contribution through the sensor reducer remains
unproven. Select a stock resolution before leaving CINE, changing physical
camera modes, or removing the SSD; those paths are not all intercepted.

Offline checks execute the actual ARM/Thumb resident, native animation and
resource parsers, image decoder, enum mapping and capture transitions. UI
registry/attachment, hardware services and final screen rendering are partly
mocked. The reports included here identify those boundaries.

## Removal

With media attached to the computer, remove `AutoRun.txt` and `FP3KMENU.BIN`
from the SD root, then remove the camera battery for 30 seconds before booting.
No flash update has been written. The installer preserves the previous version
and diagnostics in a timestamped backup recorded in
`prototype/native-menu-installation.json`.
''')
shutil.copy2(D/'native-ui/layout-repair-plan.json',P/'layout-repair-plan.json')
shutil.copy2(ROOT/'analysis/firmware/menu-integration/native-null-receiver-publisher-verification.json',P/'hud-publisher-verification.json')
archive=P.parent/(P.name+'.zip')
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for f in sorted(P.rglob('*')):
        if f.is_file():z.write(f,P.name+'/'+str(f.relative_to(P)))
print(json.dumps(dict(package=str(P),archive=str(archive),payload_sha256=sha),indent=2))
