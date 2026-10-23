# ISO -> IMX410 gain registers per gain_state (v30/v31/v8/v10 replica). See notes/ISO_MODE_SWITCH.md.
# Usage: python3 offline/iso_state_sim.py captures/isomap/isomap.json  (fits OTP-derived REF/HCG dB to live LV, then prints states 1/3/5/7)
import math,json,sys
CUR=[(100,117),(200,234),(400,468),(800,936),(1600,1872),(3200,3744),(6400,7488),(12800,14976),(25600,29952),(51200,59904),(102400,119808)]
def cal(x):
    if x<=CUR[0][0]: return CUR[0][1]
    if x>=CUR[-1][0]: return CUR[-1][1]
    for (a,b),(c,d) in zip(CUR,CUR[1:]):
        if a<=x<c: return b+(x-a)*(d-b)//(c-a)   # FUN_c04d0a20 assumed linear int
REF_DB=None; HCG_DB=None; CAP=29.97; HCG_LV_THR=12000
def v30(rel,st):
    if st==0: return int(HCG_LV_THR<rel)
    if st<4 or st in (5,6): return int(cal(640)<=rel)
    if st==7: return int(cal(3200)<=rel)
    return 0
def seg(rel,nodes,vals):
    # piecewise per decomp; implemented generically below
    pass
def v31(rel,st):
    c=cal
    if st==0:
        u2,u3=c(200),c(400)
        if rel<u2: return 100,rel
        if rel>u3: d=(u3*100+(u2>>1))//u2; return d,(rel*100+(d>>1))//d
        d=(rel*100+(u2>>1))//u2; return d,u2
    if st in (1,2,3,5,6):
        u=[c(x) for x in (100,200,320,400,500,640,800,1000,1250)]
        r=rel
        if r<u[0]: return 100,r
        if st in (1,2):
            if r<u[1]: d=((r-u[0])*100+((u[1]-u[0])>>1))//(u[1]-u[0])+100
            elif r<u[2]: d=200
            elif r<u[3]: d=int(((r-u[2])*-40+(u[3]-u[2])//2)/(u[3]-u[2]))+200
            elif r<u[4]: d=int(((r-u[3])*-35+(u[4]-u[3])//2)/(u[4]-u[3]))+160
            elif r<u[5]: d=int(((r-u[4])*-25+(u[5]-u[4])//2)/(u[5]-u[4]))+125
            elif r<u[6]: d=((r-u[5])*25+((u[6]-u[5])>>1))//(u[6]-u[5])+100
            elif r<u[7]: d=((r-u[6])*35+((u[7]-u[6])>>1))//(u[7]-u[6])+125
            elif r<u[8]: d=(((u[8]-u[7])>>1)+(r-u[7])*40)//(u[8]-u[7])+160
            else: d=200
        else:
            if r<u[1]: d=100
            elif r<u[2]: d=((r-u[1])*60)//(u[2]-u[1])+100
            elif r<u[3]: d=160
            elif r<u[4]: d=int(((r-u[3])*-35+(u[4]-u[3])//2)/(u[4]-u[3]))+160
            elif r<u[5]: d=int(((r-u[4])*-25+(u[5]-u[4])//2)/(u[5]-u[4]))+125
            elif r<u[6]: d=((r-u[5])*25+((u[6]-u[5])>>1))//(u[6]-u[5])+100
            elif r<u[7]: d=((r-u[6])*35+((u[7]-u[6])>>1))//(u[7]-u[6])+125
            elif r<u[8]: d=(((u[8]-u[7])>>1)+(r-u[7])*40)//(u[8]-u[7])+160
            else: d=200
        return d,(r*100+(d>>1))//d
    if st==7:
        u=[c(x) for x in (100,200,400,500,640,800,1600,2000,2499,3200,4001,4999)]
        r=rel
        if r<u[0]: return 100,r
        def up(i,base,k): return ((r-u[i])*k+((u[i+1]-u[i])>>1))//(u[i+1]-u[i])+base
        def dn(i,base,k): return int(((r-u[i])*-k+(u[i+1]-u[i])//2)/(u[i+1]-u[i]))+base
        if r<u[1]: d=up(0,100,100)
        elif r<u[2]: d=up(1,200,200)
        elif r<u[3]: d=up(2,400,100)
        elif r<u[4]: d=up(3,500,140)
        elif r<u[5]: d=up(4,640,160)
        elif r<u[6]: d=800
        elif r<u[7]: d=dn(6,800,160)
        elif r<u[8]: d=dn(7,640,140)
        elif r<u[9]: d=500
        elif r<u[10]: d=up(9,500,140)
        elif r<u[11]: d=up(10,640,160)
        else: d=800
        return d,(r*100+(d>>1))//d
    return 100,rel
def compose(iso,st):
    rel=cal(iso)
    h=v30(rel,st)
    dig,arel=v31(rel,st)
    db=REF_DB+20*math.log10(arel/100)
    if h: db-=HCG_DB
    over=1.0
    if db>CAP: over=10**((db-CAP)/20); db=CAP
    code=round(4095-4095*10**(-db/20))
    hi=code>=0xDFD
    r41f=(0x1D if h else 0x0E) if hi else 0
    return dict(iso=iso,rel=rel,hcg=h,v31dig=dig,arel=arel,db=round(db,2),code=code,r05E2=int(hi),r041F=r41f,
                r05A6=0x2A if h else 0x29,r05A8=0x29 if h else 0x27,overflow=round(over,3))
ISOS=[100,125,160,200,250,320,400,500,640,800,1000,1250,1600,2000,2500,3200,4000,5000,6400,8000,10000,12800,16000,20000,25600]
if __name__=='__main__':
    # fit REF/HCG from live LV (state 0)
    REF_DB=2.39-20*math.log10(1.17); HCG_DB=38.52-24.11
    live=json.load(open(sys.argv[1]))
    print('REF_DB %.3f HCG_DB %.2f'%(REF_DB,HCG_DB))
    bad=0
    for e in live:
        s=compose(e['index'],0); r=e['regs']
        ok = abs(s['code']-e['analog_code'])<=2 and s['hcg']==e['hcg'] and s['r05E2']==r['05E2'] and s['r041F']==r['041F']
        bad+= not ok
        print('LV',e['index'],s['code'],e['analog_code'],s['hcg'],e['hcg'],s['r05E2'],r['05E2'],s['r041F'],r['041F'],round(s['overflow'],3),e['soc_dgain'],'' if ok else 'MISMATCH')
    print('LV mismatches',bad)
    for st in (1,3,5,7):
        print('== state',st)
        for iso in ISOS:
            s=compose(iso,st)
            print(' %6d hcg=%d v31dig=%3d%% analog=%5.2fdB code=%4d 05E2=%d 041F=0x%02X 05A6=0x%02X 05A8=0x%02X ovf=%.3f'%(iso,s['hcg'],s['v31dig'],s['db'],s['code'],s['r05E2'],s['r041F'],s['r05A6'],s['r05A8'],s['overflow']))
