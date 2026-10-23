#!/usr/bin/env python3
"""Offline validation and research cubes from saved actual Resolve CST fixtures.

No Resolve connection, USB imports, camera I/O, firmware build or deployment.
Requires numpy, Pillow, ffmpeg; runs from any directory with explicit inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'fpSup/lut'))
from color import transfer
from cube import Cube
from ole2026 import (MeasuredMatrices,chain,cube_bytes,description,factorized_monitor,monitor,native_xyz,
                     node01,node03,q)
from resolve_cst_reference import read_exr,sha


def metrics(actual, expected):
    actual=np.asarray(actual);expected=np.asarray(expected)
    if actual.shape!=expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError('shape mismatch or nonfinite comparison')
    error=np.abs(actual-expected)
    return dict(samples=int(actual.size//3),max_abs=float(error.max()),
                p99_abs=float(np.quantile(error,.99)),rms=float(np.sqrt(np.mean(error**2))),
                max_normalized=float(np.max(error/(1+np.abs(expected)))))


def output(directory,name):
    return read_exr(directory/'vendor'/(name+'.0000.exr'))


def measure(reference):
    names=('matrix_node01','gen1_709_linear','matrix_node03','matrix_monitor')
    # Only the three unit-basis pixels calibrate each matrix; no full-chain fit.
    basis=np.eye(3)
    np.testing.assert_array_equal(read_exr(reference/'linear.exr').reshape(-1,3)[1:4],basis)
    arrays=[output(reference,n).reshape(-1,3) for n in names]
    for a in arrays:
        np.testing.assert_allclose(a[0],0,atol=2e-8)
    model=MeasuredMatrices(*(a[1:4].T for a in arrays))
    x=read_exr(reference/'linear.exr').reshape(-1,3)
    tests={name:metrics(a[4:], x[4:]@matrix.T)
           for name,a,matrix in zip(names,arrays,[model.p3_to_bwg,model.gen1_to_srgb,
                                                 model.bwg_to_dwg,model.dwg_to_709])}
    assert max(t['max_normalized'] for t in tests.values())<3e-6
    return model,tests


def compare(reference,model):
    x=read_exr(reference/'linear.exr');z=read_exr(reference/'code.exr')
    for name,image in [('linear',x),('code',z)]:
        np.testing.assert_array_equal(output(reference,'identity_'+name),image)
    branches={
        'node01':node01(x,matrices=model), 'node02':q(z,matrices=model),
        'node03':node03(z,matrices=model), 'chain':chain(x,correction=True,matrices=model),
        'bypass':chain(x,correction=False,matrices=model)}
    compared={name:metrics(value,output(reference,name)) for name,value in branches.items()}
    for name,branch in compared.items():
        # sRGB's 12.92 negative toe magnifies float32 matrix/curve roundoff.
        assert branch['max_normalized']<(1e-5 if name=='node02' else 3e-6)
    assert compared['chain']['max_abs']<1e-6
    legacy={name:metrics(value,output(reference,name)) for name,value in {
        'node01':node01(x), 'node02':q(z), 'node03':node03(z),
        'chain':chain(x,correction=True), 'bypass':chain(x,correction=False)}.items()}
    display={}
    for correction in (False,True):
        name='monitor_'+('q' if correction else 'bypass')+'_linear709_code'
        if (reference/'vendor'/(name+'.0000.exr')).exists():
            # This final display operation is ours, not an author/vendor DRT.
            expected=np.clip(output(reference,name),0,1)**(1/2.4)
            display[name]=metrics(monitor(z,'bwg-film5',correction=correction,matrices=model),expected)
            assert display[name]['max_abs']<.5/1023
    files={str(f.relative_to(reference)):sha(f) for f in sorted(reference.rglob('*')) if f.is_file()}
    return dict(float32_identity_exact=True,measured_model=compared,
                legacy_candidate=legacy,custom_display=display,files_sha256=files)


def bake(directory,model):
    directory.mkdir(exist_ok=False)
    rng=np.random.default_rng(37921)
    uniform=rng.uniform(0,1,(8192,3))
    # A second distribution: scene-linear Rec.709 chroma over eleven stops.
    linear=rng.uniform(.02,1,(8192,3))*np.exp2(rng.uniform(-8,3,(8192,1)))
    bwg=linear@np.linalg.inv(model.dwg_to_709@model.bwg_to_dwg).T
    scene=transfer(bwg,'film5')
    assert ((scene>=0)&(scene<=1)).all()
    sets={'uniform_log_cube':uniform,'scene_709_linear_m8_to_p3_ev':scene}
    for name,a in sets.items():np.save(directory/(name+'.npy'),a)
    reports={}
    for correction in (False,True):
        target={name:monitor(a,'bwg-film5',correction=correction,matrices=model) for name,a in sets.items()}
        for size in (33,65):
            name=('Q' if correction else 'bypass')+f'_BWGFilm5_to_709Gamma24_clip_{size}'
            path=directory/(name+'.cube')
            path.write_bytes(cube_bytes(size,'bwg-film5',correction=correction,matrices=model))
            cube=Cube.read(path)
            comparisons={key:metrics(cube.apply(a),target[key]) for key,a in sets.items()}
            worst=max(v['max_abs'] for v in comparisons.values())
            reports[name]=dict(file=path.name,bytes=path.stat().st_size,sha256=sha(path),
                input='BWG4/5 Film Gen5, normalized full, domain 0..1',
                output='Rec.709 D65 Gamma 2.4 normalized full',
                display='clip-linear-0-1-v1; no author DaVinci DRT',
                validation=comparisons,max_10bit_code_error=worst*1023,
                target_max_error=1/1023,passes_one_10bit_code_gate=worst<=1/1023,
                deployment_approved=False,status='research interpolation fixture')
            print(name,'max 10-bit codes',round(worst*1023,3),flush=True)
    factorized={}
    for correction in (False,True):
        key='Q' if correction else 'bypass'
        factorized[key]={name:metrics(factorized_monitor(a,correction=correction,matrices=model),
                          monitor(a,'bwg-film5',correction=correction,matrices=model))
                         for name,a in sets.items()}
        assert max(v['max_abs'] for v in factorized[key].values())<1e-8
    graph=dict(status='offline algebra verified; no ISP mapping or 1D-table approximation',
        input='BWG4/5 Film Gen5 code values; known source required',
        output='Rec.709 D65 Gamma 2.4 normalized full',
        q_graph=[dict(operation='sRGB decode scalar curve'),
                 dict(operation='linear 3x3',matrix=model.gen1_to_srgb.tolist()),
                 dict(operation='composed scalar curve',sequence=['sRGB encode','Film Gen5 decode']),
                 dict(operation='linear 3x3',matrix=(model.dwg_to_709@model.bwg_to_dwg).tolist()),
                 dict(operation='clip linear 0..1 then Gamma 2.4 encode')],
        equivalence_tests=factorized,on_camera_ready=False)
    (directory/'factorized-graph.json').write_text(json.dumps(graph,indent=2)+'\n')
    return reports,graph


def exposure(model):
    colors=np.array([[.22,.18,.12],[.40,.24,.18],[.12,.3,.2],[.1,.14,.5],
                     [.4,.08,.04],[.08,.4,.06],[.05,.08,.4],[.18]*3])
    data={};views={}
    for correction in (False,True):
        outputs=[];xy=[]
        for ev in (-2,0,2):
            code=node01(colors*2.**ev,matrices=model)
            dwg=node03(q(code,matrices=model) if correction else code,encoded=False,matrices=model)/2.**ev
            xyz=dwg@native_xyz('dwg').T
            assert (xyz.sum(-1)>0).all()
            xy.append(xyz[:,:2]/xyz.sum(-1,keepdims=True))
            rgb709=dwg@model.dwg_to_709.T
            outputs.append(np.clip(rgb709,0,1)**(1/2.4))
        xy=np.array(xy)
        delta=np.linalg.norm(xy-xy[1],axis=-1)
        key='Q' if correction else 'bypass'
        data[key]=dict(ev=[-2,0,2],p3_linear_samples=colors.tolist(),
                       xy=xy.tolist(),delta_xy_from_ev0=delta.tolist(),max_delta_xy=float(delta.max()))
        views[key]=np.array(outputs)
    assert data['bypass']['max_delta_xy']<1e-12
    assert data['Q']['max_delta_xy']>.001
    return data,views


def plot(path,views,report):
    image=Image.new('RGB',(1320,660),'#15191e');draw=ImageDraw.Draw(image)
    font_path='/System/Library/Fonts/Supplemental/Arial.ttf'
    font=ImageFont.truetype(font_path,22);small=ImageFont.truetype(font_path,17)
    draw.text((30,22),'Ole2026 CST experiment | synthetic colors, fixed Rec.709 / Gamma 2.4',font=font,fill='white')
    draw.text((30,58),'Each row applies exposure before Q, then removes it in linear light. Display uses clipping.',font=small,fill='#b5bfc8')
    x0=140;cell=138;y0=127
    for i,label in enumerate(('warm','skin-like','green','blue','red','green sat.','blue sat.','gray')):
        draw.text((x0+i*cell,y0-29),label,font=small,fill='#b5bfc8')
    for j,(branch,ev_index) in enumerate((('bypass',1),('Q',0),('Q',1),('Q',2))):
        y=y0+j*105
        label='Bypass' if branch=='bypass' else f'Q {(-2,0,2)[ev_index]:+d} EV'
        draw.text((25,y+24),label,font=small,fill='white')
        for i,color in enumerate(views[branch][ev_index]):
            c=tuple(np.round(color*255).astype(int));x=x0+i*cell
            draw.rectangle((x,y,x+126,y+79),fill=c)
    maxerr=max(r['measured_model']['chain']['max_abs'] for r in report['resolve_comparison'].values())
    draw.text((30,574),f'Actual Resolve CST check: 2 x 1,024 RGB samples | max chain code error {maxerr:.2g}',font=small,fill='#b5bfc8')
    draw.text((30,606),'Exposure dependence is demonstrated; color accuracy, DNG RAW equivalence and camera preview are unverified.',font=small,fill='#ffc482')
    image.save(path)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output',type=Path);ap.add_argument('--calibration',type=Path,required=True)
    ap.add_argument('--independent',type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    model,matrix_tests=measure(a.calibration)
    manifest=json.loads((a.calibration/'vendor/manifest.json').read_text())
    matrix_record=dict(resolve_version=manifest['resolve_version'],plugin=manifest['plugin'],
        source=str(a.calibration.resolve()),method='three unit-basis pixels per linear CST, black checked',
        matrices=model.summary(),held_out_linear_tests=matrix_tests,
        manifest_sha256=sha(a.calibration/'vendor/manifest.json'))
    (a.output/'matrices.json').write_text(json.dumps(matrix_record,indent=2)+'\n')
    report=dict(status='offline-reference-complete; camera-not-tested',camera_io=False,
        research_only=True,not_author_complete_workflow=True,
        missing=['Camera RAW P3 decode pixel match','source DNG profile and highlight recovery',
                 'unknown author nodes 04/06 and project CM','author final DaVinci DRT',
                 'paired Pyxis color accuracy','live camera tap and ISP/residual implementation'],
        sources=dict(post='https://www.facebook.com/groups/1124721801045663/permalink/3067172403467250/',
            transcription='research/imaging-hw/notes/FP_OLE_BEREK_GEN5_WORKFLOW_AUDIT_2026-09-27.md',
            gen5='bmcc6k/analysis-20260924/bmcc6k-liveview-rec709-20260924/reference/gen5_technical.txt'),
        legacy_candidate=description(),matrix_reference=matrix_record,
        resolve_comparison={str(p.resolve()):compare(p,model) for p in (a.independent,a.calibration)})
    report['cubes'],report['factorized_graph']=bake(a.output/'cubes',model)
    report['exposure'],views=exposure(model)
    report['cube_production_gate_passed']=all(c['passes_one_10bit_code_gate'] for c in report['cubes'].values())
    report['tests']=dict(matrix_normalized_error_limit=3e-6,chain_normalized_error_limit=3e-6,
                         chain_max_abs_error_limit=1e-6,node02_normalized_error_limit=1e-5,
                         monitoring_max_error_limit=.5/1023,cube_max_error_limit=1/1023)
    report['code_sha256']={str(p.relative_to(REPO)):sha(p) for p in [
        REPO/'fpSup/lut/ole2026.py',Path(__file__).resolve(),
        Path(__file__).with_name('resolve_cst_reference.py'),Path(__file__).with_name('ole2026_resolve_suite.py')]}
    plot(a.output/'comparison.png',views,report)
    report['comparison_png_sha256']=sha(a.output/'comparison.png')
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(output=str(a.output.resolve()),status=report['status'],
                         cube_production_gate_passed=report['cube_production_gate_passed']),indent=2))


if __name__=='__main__':main()
