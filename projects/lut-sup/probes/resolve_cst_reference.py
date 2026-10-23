#!/usr/bin/env python3
"""Actual ResolveFX CST in an isolated Fusion comp; no camera imports or I/O.

The Color-page RAW decoder and DRT are not part of this reference. Float EXR
I/O is first checked against negative/HDR anchors before any CST is measured.
Uses the installed vendor scripting API and ffmpeg's float32 EXR codec.
"""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import numpy as np

API=Path('/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting')
PLUGIN='ofx.com.blackmagicdesign.resolvefx.ColorSpaceTransformV2'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exr_header(path):
    data=Path(path).read_bytes()
    if data[:4]!=struct.pack('<I',20000630): raise ValueError('not an OpenEXR file')
    def cstr(at):
        end=data.index(0,at)
        return data[at:end].decode(),end+1
    at=8; attrs={}
    while data[at]:
        name,at=cstr(at);kind,at=cstr(at)
        size=struct.unpack_from('<I',data,at)[0];at+=4
        attrs[name]=(kind,data[at:at+size]);at+=size
    x0,y0,x1,y1=struct.unpack('<4i',attrs['dataWindow'][1])
    block=attrs['channels'][1];at=0;channels={}
    while block[at]:
        end=block.index(0,at);name=block[at:end].decode();at=end+1
        dtype,linear,sx,sy=struct.unpack_from('<iB3xii',block,at);at+=16
        channels[name]=dict(type=dtype,linear=linear,x_sampling=sx,y_sampling=sy)
    return dict(width=x1-x0+1,height=y1-y0+1,channels=channels)


def ffmpeg():
    exe=shutil.which('ffmpeg')
    if not exe: raise RuntimeError('ffmpeg with float32 EXR codec is required')
    return exe


def write_exr(path,image):
    path=Path(path)
    if path.exists(): raise FileExistsError(path)
    image=np.asarray(image,dtype='<f4')
    if image.ndim!=3 or image.shape[2]!=3 or not np.isfinite(image).all():
        raise ValueError('finite HxWx3 image required')
    h,w,_=image.shape
    planar=np.ascontiguousarray(image[:,:,[1,2,0]].transpose(2,0,1))
    subprocess.run([ffmpeg(),'-v','error','-n','-f','rawvideo','-pixel_format','gbrpf32le',
                    '-video_size',f'{w}x{h}','-i','pipe:0','-frames:v','1','-c:v','exr',
                    '-compression','none','-format','float','-update','1',str(path)],
                   input=planar.tobytes(),check=True)
    if any(v['type']!=2 for v in exr_header(path)['channels'].values()):
        raise RuntimeError('input EXR is not float32')


def read_exr(path):
    header=exr_header(path)
    if any(header['channels'].get(c,{}).get('type')!=2 for c in 'RGB'):
        raise ValueError('reference RGB EXR channels must be float32')
    data=subprocess.run([ffmpeg(),'-v','error','-i',str(path),'-frames:v','1',
                         '-f','rawvideo','-pix_fmt','gbrpf32le','pipe:1'],
                        capture_output=True,check=True).stdout
    planar=np.frombuffer(data,dtype='<f4').reshape(3,header['height'],header['width'])
    return planar[[2,0,1]].transpose(1,2,0).astype(np.float64)


def connect():
    sys.path.append(str(API/'Modules'))
    import DaVinciResolveScript as dvr
    resolve=dvr.scriptapp('Resolve')
    if resolve is None: raise RuntimeError('Resolve scripting connection is unavailable')
    project=resolve.GetProjectManager().GetCurrentProject()
    if project and project.IsRenderingInProgress(): raise RuntimeError('Resolve is already rendering')
    return resolve


def set_checked(tool,name,value):
    ids={v.GetAttrs()['INPS_ID']:v for v in tool.GetInputList().values()}
    if name not in ids: raise ValueError('vendor input missing: '+name)
    allowed=ids[name].GetAttrs().get('INPIDT_ComboControl_ID')
    if allowed and value not in allowed.values(): raise ValueError(f'{name}: unknown vendor enum {value}')
    tool.SetInput(name,value)
    actual=tool.GetInput(name)
    if actual!=value: raise RuntimeError(f'{name}: set {value!r}, read {actual!r}')


def cst_settings(src,src_gamma,dst,dst_gamma,cat=False):
    return dict(inputColorSpace=src,inputGamma=src_gamma,outputColorSpace=dst,outputGamma=dst_gamma,
                tmType='TM_NONE',gmType='GM_NONE',doFwdOOTF=0,doInvOOTF=0,doCAT=int(cat),
                isSrcLumMaxCustomEnabled=0,isDstLumMaxCustomEnabled=0)


def render(resolve,source,destination,nodes):
    destination=Path(destination).resolve()
    if destination.exists(): raise FileExistsError(destination)
    project=resolve.GetProjectManager().GetCurrentProject()
    if not project or project.GetName()!='LUT_Ole2026_Offline_20261021':
        raise RuntimeError('isolated research project must be selected')
    timeline=project.GetMediaPool().CreateEmptyTimeline('CST_'+destination.stem)
    if not timeline: raise RuntimeError('could not create research timeline (check for modal dialogs)')
    project.SetCurrentTimeline(timeline)
    item=timeline.InsertFusionCompositionIntoTimeline()
    if not item: raise RuntimeError('could not create research Fusion composition')
    resolve.OpenPage('fusion')
    comp=item.GetFusionCompByIndex(1)
    comp.Lock()
    comp.SetAttrs({'COMPN_RenderStart':0,'COMPN_RenderEnd':0})
    loader=comp.AddTool('Loader');loader.SetInput('Clip',str(Path(source).resolve()))
    previous=loader
    for i,settings in enumerate(nodes,1):
        tool=comp.AddTool(PLUGIN);tool.SetAttrs({'TOOLS_Name':f'CST_{i}'})
        for name,value in settings.items(): set_checked(tool,name,value)
        tool.ConnectInput('Source',previous)
        previous=tool
    saver=comp.AddTool('Saver')
    set_checked(saver,'OutputFormat','OpenEXRFormat')
    for name,value in [('OpenEXRFormat.Depth',0),('OpenEXRFormat.Compression',0),
                       ('OpenEXRFormat.AlphaEnable',0),('Gamut.ColorSpace','NoChange'),
                       ('Gamut.GammaSpace','NoChange'),('Gamut.LogType','Bypass')]:
        set_checked(saver,name,value)
    saver.SetInput('Clip',str(destination))
    saver.ConnectInput('Input',previous)
    comp.Unlock()
    comp_path=destination.with_suffix('.comp')
    if not comp.Save(str(comp_path)): raise RuntimeError('could not save reference composition')
    completed=comp.Render({'Start':0,'End':0,'Wait':True,'Tool':saver,
                           'HiQ':True,'Proxy':False,'Force':True})
    if not completed or not destination.exists():
        raise RuntimeError(f'Resolve render failed: {completed}; expected {destination}')
    image=read_exr(destination)
    record=dict(plugin=PLUGIN,resolve_version=resolve.GetVersionString(),nodes=nodes,
                source_sha256=sha(source),output_sha256=sha(destination),
                composition_sha256=sha(comp_path),exr=exr_header(destination))
    destination.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
    return image


def render_many(resolve, directory, jobs):
    """One timeline comp and render transaction, so one completion dialog only."""
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    project=resolve.GetProjectManager().GetCurrentProject()
    if not project or project.GetName()!='LUT_Ole2026_Offline_20261021':
        raise RuntimeError('isolated research project must be selected')
    timeline=project.GetMediaPool().CreateEmptyTimeline('CST_'+directory.parent.name+'_'+directory.name)
    if not timeline: raise RuntimeError('could not create research timeline (check modal dialogs)')
    project.SetCurrentTimeline(timeline)
    item=timeline.InsertFusionCompositionIntoTimeline()
    resolve.OpenPage('fusion')
    comp=item.GetFusionCompByIndex(1)
    comp.Lock()
    records={}
    for index,(name,job) in enumerate(jobs.items()):
        source=Path(job['source']).resolve()
        loader=comp.AddTool('Loader');loader.SetAttrs({'TOOLS_Name':name+'_input'})
        loader.SetInput('Clip',str(source))
        previous=loader
        for i,settings in enumerate(job['nodes'],1):
            tool=comp.AddTool(PLUGIN);tool.SetAttrs({'TOOLS_Name':f'{name}_CST{i}'})
            for key,value in settings.items():set_checked(tool,key,value)
            tool.ConnectInput('Source',previous);previous=tool
        saver=comp.AddTool('Saver');saver.SetAttrs({'TOOLS_Name':name+'_output'})
        set_checked(saver,'OutputFormat','OpenEXRFormat')
        for key,value in [('OpenEXRFormat.Depth',0),('OpenEXRFormat.Compression',0),
                          ('OpenEXRFormat.AlphaEnable',0),('Gamut.ColorSpace','NoChange'),
                          ('Gamut.GammaSpace','NoChange'),('Gamut.LogType','Bypass')]:
            set_checked(saver,key,value)
        output=directory/(name+'.0000.exr')
        saver.SetInput('Clip',str(output));saver.ConnectInput('Input',previous)
        records[name]=dict(source=str(source),source_sha256=sha(source),
                           output=str(output),nodes=job['nodes'])
    comp.Unlock()
    comp_path=directory/'reference.comp';assert comp.Save(str(comp_path))
    completed=comp.Render({'Start':0,'End':0,'Wait':True,'HiQ':True,'Proxy':False,'Force':True})
    if not completed:raise RuntimeError('vendor suite render failed; dismiss warning before retry')
    images={}
    for name,record in records.items():
        images[name]=read_exr(record['output'])
        record.update(output_sha256=sha(record['output']),exr=exr_header(record['output']))
    manifest=dict(resolve_version=resolve.GetVersionString(),plugin=PLUGIN,
                  host='Resolve Fusion timeline composition; not Camera RAW',
                  composition_sha256=sha(comp_path),jobs=records)
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return images


def main():
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output',type=Path,help='new output directory for float transport check')
    a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    source=np.array([[[-.2,.18,16.],[4.,-.002,1.],[0.,0.,0.],[.1,.4,.9]],
                     [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.],[1.,1.,1.]]],dtype=np.float32)
    write_exr(a.output/'source.exr',source)
    np.testing.assert_array_equal(read_exr(a.output/'source.exr'),source)
    actual=render(connect(),a.output/'source.exr',a.output/'identity.0000.exr',[])
    np.testing.assert_array_equal(actual,source)
    print(json.dumps(dict(transport='float32 identity passed',samples=source.shape[0]*source.shape[1],
                         min=float(actual.min()),max=float(actual.max())),indent=2))


if __name__=='__main__': main()
