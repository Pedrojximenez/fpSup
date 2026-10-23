#!/usr/bin/env python3
"""Bounded mode102 experiment. Explicit --run-live required. No card deployment.

Uses maintained callfn.S/getfile.S, full RAM readback, ROM cache publication,
the shared AF lease, bounded directory API, and MEM1 for owned file buffers.
Does not use the legacy fpcam.record retry/toggle behavior.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import re
import struct
import sys
import time
from pathlib import Path

import spatial_hdr_probe as probe

ROOT=probe.ROOT
sys.path.insert(0,str(ROOT/'projects/fp-af-assist'))
from focus_bridge import Transport
sys.path.insert(0,str(probe.SHELL))
from armasm import assemble

ECHO=0xC0BAC2F8
ECHO_ORIG=0xC03D99A0
WATCH=('SetMovRecSize','SetMovFramerate','SetMovCinemaDNGQuality',
       'SetMovRecFormat','SetCropMode','SetIso','SetExpMode',
       'SetShutterSpeedSettingMode','SetShutterSpeed','SetShutterAngle')
CHANGES=(('SetMovFramerate',3),('SetCropMode',1),('SetMovRecSize',3),('SetIso',100))


class Live:
    def __init__(self,out):
        self.out=out
        self.log=(out/'live.jsonl').open('x')
        self.io=Transport(event=self.event)
        self.memory=None
        self.claim=None

    def event(self,row):
        row=dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**row)
        self.log.write(json.dumps(row,ensure_ascii=False)+'\n');self.log.flush()

    def shell(self,cmd,ms=1000):
        self.io.assert_motion_transport_healthy()
        return self.io.shell(cmd,timeout_ms=ms).strip()

    def words(self,addr,n=1):
        out=[]
        for off in range(0,n,8):
            take=min(8,n-off);at=addr+4*off
            reply=self.shell(f'mem get 0x{at:08X},,0x{take*4:X}')
            out.extend(self.io._memory_words(reply,at,take))
        return out

    def write(self,addr,data):
        data=bytes(data)
        if len(data)%4:raise ValueError('word aligned data required')
        want=struct.unpack(f'<{len(data)//4}I',data)
        for attempt in range(3):
            got=self.words(addr,len(want))
            bad=[i for i,v in enumerate(want) if got[i]!=v]
            if not bad:return
            for i in bad:
                self.shell(f'mem set 0x{addr+4*i:08X} 0x{want[i]:08X}')
        if self.words(addr,len(want))!=list(want):raise RuntimeError('RAM write did not verify')

    def put32(self,addr,value):self.write(addr,struct.pack('<I',value))

    def exchange_handler(self,expected,target):
        if self.words(ECHO)!=[expected]:raise RuntimeError('echo owned by another caller')
        self.put32(ECHO,target)

    def echo(self,target):
        self.exchange_handler(ECHO_ORIG,target)
        try:
            return self.shell('echo',ms=5000)
        finally:
            # Never infer handler return after an uncertain transport event.
            if not self.io.transport_faulted:
                self.exchange_handler(target,ECHO_ORIG)

    def publish(self):
        for fn in (0xC000E91C,0xC000EABC):self.echo(fn)

    def idle(self):
        if self.shell('status get is_recording')!='is_recording -> 0':
            raise RuntimeError('recording already active')
        w=self.words(0xC30338C8,3)
        if w[0] or w[2]&255 or self.words(0xC3033A6C)[0]:
            raise RuntimeError('capture/shutter busy')
        if self.words(0xC31C01B0)!=[1] or self.words(0xC31F86E0)!=[1]:
            raise RuntimeError('physical/applied CINE rejected')

    def init_memory(self):
        if self.memory:return
        self.idle()
        import cave
        import putfile
        # These names/ranges are maintained by the existing host tools.
        parm,code=putfile.P,putfile.CODE
        pool,size,worker=self.words(0xC072F050,3)
        if not (0x44000000<=pool<0x80000000 and size>=0x10400):
            raise RuntimeError('worker pool publication rejected')
        fobj=pool+0x10000
        if pool<=worker<pool+size and fobj<worker+0x1000:
            raise RuntimeError('file scratch could overlap worker code')
        self.memory=dict(parm=parm,code=code,fobj=fobj,pool=pool,pool_size=size,
                         boot=self.words(0xC072F6F8)[0])
        self.event(dict(event='memory_ownership',memory=self.memory))
        self.native_blob=assemble(probe.SHELL/'asm/callfn.S',[f'P=0x{parm:X}'])
        self.file_blob=assemble(probe.SHELL/'asm/getfile.S',[f'P=0x{parm:X}'])
        if max(len(self.native_blob),len(self.file_blob))>512:raise RuntimeError('IO code too large')

    def native(self,fn,*args):
        if fn not in (0xC0366918,0xC0366990,0xC03669F8,0xC0366940,0xC001D7A0):
            raise ValueError('unreviewed native call')
        self.init_memory();p=self.memory['parm'];code=self.memory['code']
        argv=list(args)+[0]*(4-len(args))
        self.write(code,self.native_blob)
        self.write(p,struct.pack('<10I',fn,*argv,0,0,0,0,0))
        self.publish();self.echo(code)
        ret,done=self.words(p+0x18,2)
        if done!=0xD09E0000:raise RuntimeError('native helper did not finish')
        return ret

    def entries(self,path,limit=16):
        self.init_memory();p=self.memory['parm'];entry=self.memory['fobj']
        holder=p+0x80;name=p+0xA0
        raw=path.encode('ascii')+b'\0'
        if len(raw)>64:raise ValueError('directory path too long')
        self.put32(holder,0)
        self.write(name,raw+b'\0'*(-len(raw)%4))
        # Native dir uses the selected mounted volume, not an assumed drive.
        drive=self.words(0xC2F20884)[0]
        if drive not in (1,2,3,5):raise RuntimeError('unknown directory volume')
        self.native(0xC0366918,holder,drive)
        out=[]
        try:
            if not self.native(0xC0366990,holder,name):raise RuntimeError('directory open failed')
            for _ in range(limit):
                self.write(entry,bytes(0x238))
                if not self.native(0xC03669F8,holder,entry):break
                data=struct.pack('<142I',*self.words(entry,142))
                text=data[:0x210].decode('utf-16le').split('\0')[0]
                size=struct.unpack_from('<Q',data,0x210)[0]
                out.append(dict(name=text,size=size,attr=data[0x218]))
        finally:
            if not self.io.transport_faulted:self.native(0xC0366940,holder,2)
        self.event(dict(event='bounded_directory',path=path,limit=limit,entries=out))
        return out

    def file(self,remote,size,local):
        self.init_memory();p=self.memory['parm'];code=self.memory['code']
        raw=remote.encode('ascii')+b'\0'
        if len(raw)>0xB0 or not 0<size<32*1024*1024:raise ValueError('file size/path rejected')
        values=[0]*9
        values[5]=0;values[6]=size+4096;values[7]=self.memory['fobj'];values[8]=1
        self.write(p,struct.pack('<9I',*values))
        self.write(p+0x24,raw+b'\0'*(-len(raw)%4))
        self.write(code,self.file_blob)
        self.publish();self.echo(code)
        actual,status,opened,read=self.words(p+4,4)
        buf=self.words(p+0x14)[0]
        self.event(dict(event='file_read_status',remote=remote,actual=actual,status=status,
                        opened=opened,read=read,buffer=buf))
        if status!=2 or not opened or not read or actual!=size or not 0x44000000<=buf<0x80000000:
            raise RuntimeError('file buffer/status uncertain; retained for diagnosis')
        import putfile
        caps=putfile.mem_caps(refresh=True)
        if not caps or caps['windows'][7]!=(0,0,0):
            raise RuntimeError('MEM1 transient window unavailable; retained buffer')
        can_free=False
        try:
            try:
                putfile.mem_window(7,buf,size,1)
            except BaseException:
                self.io._latch_transport_fault()
                self.event(dict(event='buffer_retained',buffer=buf,size=size,
                                reason='MEM1 window grant uncertain; no revoke or free'))
                raise
            try:
                data=putfile.mem_read(buf,size,sync=True)
            except BaseException:
                self.io._latch_transport_fault()
                self.event(dict(event='buffer_retained',buffer=buf,size=size,
                                reason='MEM1 outcome uncertain; no revoke or free'))
                raise
            try:
                putfile.mem_window(7,0,0,0)
            except BaseException:
                self.io._latch_transport_fault()
                self.event(dict(event='buffer_retained',buffer=buf,size=size,
                                reason='MEM1 window revoke uncertain; no free'))
                raise
            can_free=True
            if len(data)!=size:raise RuntimeError('short file transfer')
            local.write_bytes(data)
            self.event(dict(event='file_saved',remote=remote,local=str(local),size=size,
                            sha256=hashlib.sha256(data).hexdigest()))
        finally:
            if can_free and not self.io.transport_faulted:self.native(0xC001D7A0,p+0xE0,2)

    def clip_names(self):
        return set(re.findall(r'\bA\d{3}_\d{3}\b',self.shell('dir \\CINEMA',ms=3000)))

    def key_pair(self):
        self.shell('key MOVON')
        time.sleep(.12)
        self.shell('key MOVOFF')

    def record(self,label):
        self.idle();before=self.clip_names()
        self.key_pair()
        time.sleep(.15)
        observed=dict(sensor_mode=self.words(0xC343B58C)[0],
                      gain_state=self.words(0xC343A6AC)[0],
                      analog_code=self.words(0xC343B5A8)[0],
                      cg=self.words(0xC343B5BC)[0]&255,
                      sensor_digital_gain=self.words(0xC343B5B8)[0],
                      atomic=False,exposure_aligned=False)
        self.event(dict(event='record_mode_observation',label=label,**observed))
        time.sleep(.75)
        # A card may already have auto-stopped. Never toggle a stopped clip.
        state=self.shell('status get is_recording')
        if state=='is_recording -> 1':self.key_pair()
        elif state!='is_recording -> 0':raise RuntimeError('unknown recording state')
        time.sleep(1.5)
        for _ in range(15):
            w=self.words(0xC30338C8,3)
            if not w[0] and not w[2]&255:break
            time.sleep(.2)
        self.idle()
        new=self.clip_names()-before
        if len(new)!=1:raise RuntimeError(f'new clip identity rejected: {new}')
        clip=new.pop();self.event(dict(event='new_clip',label=label,clip=clip))
        self.last_record=dict(clip=clip,**observed)
        if observed['sensor_mode']!=102 or observed['gain_state']!=7 or observed['cg']!=0:
            raise RuntimeError('recorded mode/gain context is not mode102 / RAW12 / LCG')
        print(f'{label}: new clip {clip}',flush=True)
        return clip

    def fetch_samples(self,clip,label):
        entries=self.entries('\\CINEMA\\'+clip)
        frames=sorted((x for x in entries if x['name'].lower().endswith('.dng')),
                      key=lambda x:x['name'])
        if len(frames)<4:raise RuntimeError('fewer than four DNG frames')
        samples=frames[4:8] if len(frames)>=8 else frames[-4:]
        folder=self.out/label;folder.mkdir()
        for x in samples:
            self.file('\\CINEMA\\'+clip+'\\'+x['name'],x['size'],folder/x['name'])
        return folder

    def snapshot(self):return {k:self.shell('menu '+k) for k in WATCH}

    def set_menu(self,k,v):
        self.idle();self.shell(f'menu {k} {v}');time.sleep(.25)
        actual=self.shell('menu '+k)
        self.event(dict(event='setting',name=k,wanted=str(v),actual=actual))
        if actual!=str(v):raise RuntimeError(f'{k} did not become {v}: {actual}')


def run(out,baseline_only=False):
    with open('/tmp/fp-af-fusion.lock','a+') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cam=Live(out)
        original=cam.snapshot()
        (out/'original_settings.json').write_text(json.dumps(original,indent=2))
        changed=[];installed=False;meta=None
        try:
            cam.idle()
            if original['SetMovRecFormat']!='0' or original['SetMovCinemaDNGQuality']!='0':
                raise RuntimeError('native CinemaDNG / 12-bit baseline required')
            if cam.words(probe.SLOT)!=[probe.ORIGINAL]:raise RuntimeError('gain writer already borrowed')
            for k,v in CHANGES:
                if original[k]!=str(v):
                    changed.append(k);cam.set_menu(k,v)
            print('mode102 candidate configured; capturing native baseline',flush=True)
            cam.event(dict(event='prepared',settings=cam.snapshot(),mode=cam.shell('imager mode_now')))
            clip=cam.record('baseline_stock')
            folder=cam.fetch_samples(clip,'baseline_stock')
            if baseline_only:return
            # Full matrix is a separate explicit continuation after baseline QA.
            raise RuntimeError('baseline QA must be reviewed before matrix installation')
        finally:
            if installed and not cam.io.transport_faulted:
                cam.put32(meta['state']+4,0);cam.publish()
                if cam.words(probe.SLOT)!=[meta['address']]:raise RuntimeError('gain hook owner changed')
                cam.put32(probe.SLOT,probe.ORIGINAL);cam.publish()
            if not cam.io.transport_faulted:
                # Restore the original resolution before its higher frame rate.
                order=('SetMovRecSize','SetCropMode','SetMovFramerate','SetIso')
                for k in order:
                    if k in changed:cam.set_menu(k,original[k])
                after=cam.snapshot()
                cam.event(dict(event='restored',settings=after,expected=original,
                               equal=after==original,gain_slot=cam.words(probe.SLOT)))
                if after!=original:raise RuntimeError('original settings not restored')
            else:cam.event(dict(event='restore_deferred',reason='transport outcome uncertain'))
            cam.log.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-live',action='store_true')
    p.add_argument('--baseline-only',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.run_live or not a.baseline_only:p.error('explicit --run-live --baseline-only required')
    a.output.mkdir(parents=True,exist_ok=False)
    run(a.output,baseline_only=True)


if __name__=='__main__':main()
