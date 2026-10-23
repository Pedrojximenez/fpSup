#!/usr/bin/env python3
"""Synthetic vendor CST references. Creates only the dedicated research timeline."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'fpSup/lut'))
from color import transfer
from resolve_cst_reference import connect,cst_settings,render_many,write_exr,read_exr

# Resolve 21.0.4 Inspector label verified: Wide Gamut Gen 4 / 5 uses this legacy ID.
BWG_ID='BMD4KBCASTFILM'


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path)
    ap.add_argument('--seed',type=int,default=20261021)
    a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    rng=np.random.default_rng(a.seed)
    linear=np.exp2(rng.uniform(-10,5,(1024,3)))
    linear[:10]=[[0,0,0],[1,0,0],[0,1,0],[0,0,1],[1,1,1],
                 [.18]*3,[-.02]*3,[-.02,.18,16],[4,-.002,1],[.001,.001,.001]]
    code=rng.uniform(-.03,1.2,(1024,3))
    code[:12]=[[0]*3,[.18]*3,[1]*3,[-.02]*3,[.5,.3,.2],
               [.25,.4,.33],[.04045]*3,[.0031308]*3,[.09246575342465753]*3,
               [1,0,0],[0,1,0],[0,0,1]]
    for name,image in [('linear',linear),('code',code)]:
        write_exr(a.output/(name+'.exr'),image.astype(np.float32).reshape(16,64,3))
        np.testing.assert_array_equal(read_exr(a.output/(name+'.exr')),
                                      image.astype(np.float32).reshape(16,64,3))
    # All enum IDs are read from the installed tool; don't infer BWG from its ID.
    bmd_ids=['BMDFILM','BMD4KFILM','BMD4KFILMV3','BMD4KVIDEOV3','BMD46KFILM',
             'BMD46KFILMV3','BMD46KVIDEOV3','BMDPOCKET4KFILM','BMD4KBCASTVIDEO',
             'BMD4KBCASTFILM','BMDVIDEOV5']
    jobs={}
    def add(name,source,nodes): jobs[name]=dict(source=a.output/(source+'.exr'),nodes=nodes)
    def c(src,sg,dst,dg,cat=False):
        return cst_settings(src+'_COLORSPACE',sg+'_GAMMA',dst+'_COLORSPACE',dg+'_GAMMA',cat)
    for name in ('linear','code'):add('identity_'+name,name,[])
    for id in bmd_ids:add(id+'_xyz','linear',[c(id,'LINEAR','XYZ','LINEAR')])
    add('gen1_709_linear','linear',[c('BMDFILM','LINEAR','REC709','LINEAR')])
    add('srgb_decode','code',[c('REC709','SRGB','REC709','LINEAR')])
    add('srgb_encode','linear',[c('REC709','LINEAR','REC709','SRGB')])
    add('film5_decode','code',[c(BWG_ID,'BMDFILMV5',BWG_ID,'LINEAR')])
    add('film5_encode','linear',[c(BWG_ID,'LINEAR',BWG_ID,'BMDFILMV5')])
    n1=c('P3D60','LINEAR',BWG_ID,'BMDFILMV5',True)
    n2=c('BMDFILM','SRGB','SRGB','SRGB')
    n3=c(BWG_ID,'BMDFILMV5','DWG','DAV_INTER_OETF')
    add('node01','linear',[n1]);add('node02','code',[n2]);add('node03','code',[n3])
    add('chain','linear',[n1,n2,n3]);add('bypass','linear',[n1,n3])
    add('matrix_node01','linear',[c('P3D60','LINEAR',BWG_ID,'LINEAR',True)])
    add('matrix_node03','linear',[c(BWG_ID,'LINEAR','DWG','LINEAR')])
    add('matrix_monitor','linear',[c('DWG','LINEAR','REC709','LINEAR')])
    n4=c('DWG','DAV_INTER_OETF','REC709','LINEAR')
    add('monitor_q_linear709_code','code',[n2,n3,n4])
    add('monitor_bypass_linear709_code','code',[n3,n4])
    images=render_many(connect(),a.output/'vendor',jobs)
    for name in ('linear','code'):
        np.testing.assert_array_equal(images['identity_'+name],read_exr(a.output/(name+'.exr')))
    print(json.dumps(dict(jobs=len(images),float32_identity_exact=True,
                         output=str(a.output.resolve())),indent=2))


if __name__=='__main__':main()
