/* Included after ogc.c's helpers. One common dynamic row, any registered
 * producer. Table/profile budgets belong to the active recipe, not producers.
 * NBR bytes are immutable for the whole boot: firmware may retain readers. */
struct vrc_pack { u32 at, bytes, hash; };
struct vrc_state {
    u32 magic, abi, lock, provider, generation, result, detail;
    u32 count, packs, asset_used, row;
    struct vrc_provider providers[VRC_MAX_PROVIDERS];
    struct vrc_pack assets[VRC_MAX_PACKS];
};

static int ogc_virtual_unready(u8 *S, u32 row)
{
    struct vrc_state *v=(struct vrc_state *)(uintptr_t)SW(S,S_VRC);
    return v && row==v->row && !v->generation;
}

static int ogc_virtual_active(u8 *S, u32 row)
{
    struct vrc_state *v=(struct vrc_state *)(uintptr_t)SW(S,S_VRC);
    return v && row==v->row && v->generation;
}

static u32 vrc_finish(struct vrc_state *v, u32 result, u32 detail)
{
    v->result=result; v->detail=detail; dmb(); v->lock=0;
    return result;
}

static u32 vrc_apply(u8 *S, struct vrc_state *v, u32 id)
{
    if (v->lock) return VRC_REENTER;
    v->lock=1;
    if (busy()) return vrc_finish(v,VRC_BUSY,0);
    if (!W(rowp(S,v->row)+ROW_ON) || !W(rowp(S,v->row)+ROW_MROW))
        return vrc_finish(v,VRC_NOT_READY,0);
    struct vrc_provider *pr=0;
    for (u32 i=0;i<v->count;i++) if (v->providers[i].id==id) pr=v->providers+i;
    if (!pr) return vrc_finish(v,VRC_BAD_PROVIDER,0);
    u32 obj=((fw0)GET_OBJ)(), fmt=((fw1)GET_FMT)(obj);
    if (fmt) return vrc_finish(v,VRC_FORMAT,fmt);
    u32 rate=SW(S,S_VRATE);
    if (!rate) rate=rank_of(((fw1)FR_GET)(obj));
    struct vrc_input in={sizeof(in),VRC_ABI,rate,fmt};
    struct vrc_blob blob={0,0};
    u32 rc=pr->build(pr->context,&in,&blob);
    if (rc) return vrc_finish(v,VRC_BUILD,rc);
    if (!blob.data || (blob.data&3u) || blob.bytes<RCD_HDR || blob.bytes>RCD_MAX_FILE ||
        (blob.bytes&3u) || blob.data+blob.bytes<blob.data)
        return vrc_finish(v,VRC_BAD_RCD,WHY_SIZE);
    u32 stage=((u32)(uintptr_t)(v+1)+63u)&~63u, fo=stage+OGC_S_BYTES;
    u32 raw=fo+0x1000u+(v->generation&1u)*RCD_MAX_FILE;

    copy(raw,blob.data,blob.bytes);
    rc=rcd_check(S,raw,blob.bytes);
    if (rc) return vrc_finish(v,VRC_BAD_RCD,rc);
    u32 boot=W(SW(S,S_FOBJ)+FO_FILES+4u*v->row);
    /* The resolution entry has one stable identity, independent of producer. */
    W(raw+RH_LABEL)=W(boot+RH_LABEL); W(raw+RH_LABEL+4)=W(boot+RH_LABEL+4);
    W(raw+RH_ENUM)=W(boot+RH_ENUM);
    u32 ln, pack=sec(raw,SEC_PACK,&ln), ph=fnv(pack,ln), saved=0, fresh=0;
    for (u32 i=0;i<v->packs;i++) {
        struct vrc_pack *a=v->assets+i;
        if (a->bytes!=ln || a->hash!=ph) continue;
        u32 same=1;
        for (u32 k=0;k<ln;k++) if (B8(a->at+k)!=B8(pack+k)) { same=0; break; }
        if (same) { saved=a->at; break; }
    }
    if (!saved) {
        if (v->packs==VRC_MAX_PACKS || ((ln+3u)&~3u)>VRC_ASSET_BYTES-v->asset_used)
            return vrc_finish(v,VRC_FULL,ln);
        fresh=1;
    }
    /* Preflight the same production compiler in owned scratch. No live table
     * changes before validation, resource budgeting and rate checks pass. */
    copy(stage,(u32)(uintptr_t)S,S_BODY);
    copy(fo,SW(S,S_FOBJ),0x1000u);
    u8 *T=(u8 *)(uintptr_t)stage;
    SW(T,S_FOBJ)=fo;
    W(fo+FO_FILES+4u*v->row)=raw;
    if (!fill_s(T,SW(S,S_NROWS))) return vrc_finish(v,VRC_FULL,WHY_S_FULL);
    u32 supported=0, generated[G_BYTES/4u];
    for (u32 i=0;i<SW(T,S_NENT);i++) {
        u32 e=entp(T,i);
        if (W(e+ENT_ROW)==v->row && gen_entry(raw,i-W(rowp(T,v->row)+ROW_ENT0),(u32)(uintptr_t)generated) && generated[G_RANK/4u]==rate) supported=1;
        W(e+ENT_KEYPTR)=(u32)(uintptr_t)S+SW(T,S_ENTS)+ENT_SIZE*i+ENT_KEY;
    }
    if (!supported) return vrc_finish(v,VRC_RATE,rate);
    for (u32 i=0;i<SW(S,S_NROWS);i++) {
        u32 from=rowp(S,i),to=rowp(T,i);
        /* UI identities are installed once and remain at stable row offsets. */
        copy(to+ROW_MROW,from+ROW_MROW,ROW_UIRES+4u-ROW_MROW);
        W(to+ROW_ON)=W(from+ROW_ON);
        if (i==v->row) {
            W(to+ROW_PACK)=saved; W(to+ROW_PACKLEN)=ln;
            if (W(from+ROW_PACK)!=saved) { W(to+ROW_PACKCTX)=0; W(to+ROW_PACKST)=0; }
        }
    }
    if (busy()) return vrc_finish(v,VRC_BUSY,0);
    /* Stop the live-view owner before replacing buffers readers may hold.
     * The usual camera scheduler transition is restored after restart. */
    u32 holder=((fw0)LV_HOLDER)(), running=0, cs=0, was=6;
    if (holder && W(holder) && W(W(holder)+4)) {
        running=1; cs=((fw0)CAMSCH1)(); was=((fw1)CS_GET)(cs);
        if (was!=6) ((fw2)CS_SET)(cs,6);
        ((fw1)LV_STOP)(holder);
    }
    if (busy()) {
        if (running) { ((fw1)LV_START)(holder); if (was!=6) ((fw2)CS_SET)(cs,was); }
        return vrc_finish(v,VRC_BUSY,0);
    }
    u32 heap=0;
    if (fresh) {
        heap=((fw1)0xC001CF78u)(0);
        saved=heap ? ((u32 (*)(u32,u32,u32,u32,u32))0xC001D038u)(heap,(ln+3u)&~3u,0,0,0) : 0;
        if (!saved) {
            if (running) { ((fw1)LV_START)(holder); if (was!=6) ((fw2)CS_SET)(cs,was); }
            return vrc_finish(v,VRC_FULL,ln);
        }
        W(rowp(T,v->row)+ROW_PACK)=saved;
        for (u32 i=0;i<ln;i++) B8(saved+i)=B8(pack+i);
    }
    u32 irq=irq_off();
    if (busy()) {
        irq_restore(irq);
        if (fresh) ((fw2)0xC001D2B8u)(heap,saved);
        if (running) { ((fw1)LV_START)(holder); if (was!=6) ((fw2)CS_SET)(cs,was); }
        return vrc_finish(v,VRC_BUSY,0);
    }
    if (fresh) {
        struct vrc_pack *a=v->assets+v->packs++;
        a->at=saved; a->bytes=ln; a->hash=ph;
        v->asset_used+=(ln+3u)&~3u;
    }
    SW(S,S_FLAG)=0; dmb();
    copy((u32)(uintptr_t)S+S_BODY,stage+S_BODY,SW(T,S_S_END)-S_BODY);
    copy((u32)(uintptr_t)S+S_NROWS,stage+S_NROWS,S_VMID0+4u-S_NROWS);
    copy((u32)(uintptr_t)S+S_VMDONOR,stage+S_VMDONOR,4u*OGC_MAX_VMS);
    SW(S,S_NVAR)=SW(T,S_NVAR); SW(S,S_VARS)=SW(T,S_VARS); SW(S,S_S_END)=SW(T,S_S_END);
    copy((u32)(uintptr_t)S+S_BASEROW,stage+S_BASEROW,4u*OGC_MAX_ROWS);
    copy((u32)(uintptr_t)S+S_BINFILT,stage+S_BINFILT,4u*OGC_MAX_ROWS);
    W(SW(S,S_FOBJ)+FO_FILES+4u*v->row)=raw;
    SW(S,S_PICKOK)=0; SW(S,S_FPSLATCH)=0; SW(S,S_LAST_ENT)=0;
    SW(S,S_PBROW)=0; SW(S,S_CUR)=0; SW(S,S_ASPECT)=0;
    SW(S,S_SEL)=v->row+1u; SW(S,S_DIRTY)=1;
    v->provider=id; v->generation++;
    dmb(); irq_restore(irq);
    pairs_build(S);
    /* Use the actual setter so UHD -> the dynamic FHD-backed row is coherent. */
    ((fw2)0xC005C020u)(obj,W(rowp(S,v->row)+ROW_STOCK));
    u32 list[3]={EXCL_FRAMERATE,EXCL_BITDEPTH,0xffffffffu};
    ((fw2)EXCL_RECOMPUTE)(((fw0)EXCL_MGR)(),(u32)(uintptr_t)list);
    if (running) { ((fw1)LV_START)(holder); if (was!=6) ((fw2)CS_SET)(cs,was); }
    return vrc_finish(v,VRC_OK,0);
}

u32 ogc_virtual_dispatch(uintptr_t ctx,u32 op,uintptr_t arg)
{
    u8 *S=(u8 *)ctx;
    /* the declared rates: every consumer, with or without a dynamic row */
    if (op==VRC_RATES) return ogc_rate_list(S,(struct vrc_rates *)arg);
    if (op==VRC_RATE_SET) return ogc_rate_set(S,(u32)arg);
    struct vrc_state *v=(struct vrc_state *)(uintptr_t)SW(S,S_VRC);
    if (!v || v->magic!=VRC_MAGIC || v->abi!=VRC_ABI) return VRC_NOT_READY;
    if (op==VRC_SETTINGS) {
        if (busy()) return VRC_BUSY;
        if (!v->count) return VRC_NOT_READY;
        struct vrc_provider *p=v->providers;
        for (u32 i=0;i<v->count;i++) if (v->providers[i].id==v->provider) p=v->providers+i;
        return p->settings ? p->settings(p->context,1) : VRC_NOT_READY;
    }
    if (op==VRC_REGISTER) {
        const struct vrc_provider *p=(const struct vrc_provider *)arg;
        if (!p || p->bytes!=sizeof(*p) || p->abi!=VRC_ABI) return VRC_BAD_ABI;
        if (!p->id || !p->build || p->capabilities || p->reserved) return VRC_BAD_PROVIDER;
        for (u32 i=0;i<v->count;i++) if (v->providers[i].id==p->id) {
            /* Re-registration is idempotent only for the same resident owner. */
            const struct vrc_provider *old=v->providers+i;
            return old->context==p->context && old->build==p->build && old->settings==p->settings ? VRC_OK : VRC_BAD_PROVIDER;
        }
        if (v->count==VRC_MAX_PROVIDERS) return VRC_FULL;
        copy((u32)(uintptr_t)(v->providers+v->count++),arg,sizeof(*p));
        return VRC_OK;
    }
    if (op==VRC_APPLY) return vrc_apply(S,v,(u32)arg);
    if (op==VRC_STATUS) {
        struct vrc_status *out=(struct vrc_status *)arg;
        if (!out || out->bytes!=sizeof(*out) || out->abi!=VRC_ABI) return VRC_BAD_ABI;
        out->provider=v->provider; out->generation=v->generation; out->result=v->result;
        out->detail=v->detail; out->providers=v->count; out->asset_bytes=v->asset_used;
        return VRC_OK;
    }
    return VRC_BAD_ABI;
}

/* Generic Help routing: the active producer supplies its own settings page.
 * 0 means the producer isn't ready; the shim uses the stock Help page then.
 * 0xffffffff means an unrelated name and preserves the native call exactly. */
u32 ogc_virtual_gui(u8 *S,u32 name)
{
    if (name && B8(name)=='R' && B8(name+1)=='C' && B8(name+2)=='_' && B8(name+3)=='F' &&
        B8(name+4)=='I' && B8(name+5)=='L' && B8(name+6)=='E' && B8(name+7)=='S' && !B8(name+8)) return 21u;
    if (!name || B8(name)!='V' || B8(name+1)!='R' || B8(name+2)!='C' || B8(name+3)!='_' ||
        B8(name+4)!='S' || B8(name+5)!='E' || B8(name+6)!='T' || B8(name+7)!='T' ||
        B8(name+8)!='I' || B8(name+9)!='N' || B8(name+10)!='G' || B8(name+11)!='S' || B8(name+12)) return 0xffffffffu;
    struct vrc_state *v=(struct vrc_state *)(uintptr_t)SW(S,S_VRC);
    if (!v || !v->count) return 0;
    struct vrc_provider *p=v->providers;
    for (u32 i=0;i<v->count;i++) if (v->providers[i].id==v->provider) p=v->providers+i;
    return p->settings ? p->settings(p->context,0) : 0;
}
