/* Native RES-CUSTOM settings, independent of virtual-RCD producers. */
enum { RC_VISIBLE=5, RC_TABS=4, RC_STRINGS=128,
       RC_KEY=0, RC_FOCUS, RC_FILE, RC_ON, RC_COUNT, RC_STATUS, RC_RESTART,
       RC_ROWS, RC_PARTS=12, RC_N=0, RC_G, RC_V, RC_R, RC_E, RC_VIS, RC_LOCK,
       RC_SELECTED, RC_MORE, RC_DEFAULT, RC_CHOICE, RC_VERSIONX,
       RC_TAB=RC_ROWS+RC_VISIBLE*RC_PARTS, RC_TITLE=RC_TAB+RC_TABS*4, RC_VARS=RC_TITLE+1 };
struct rc_ui {
    u32 magic, state, S, blob, app, index, desc;
    u32 names[RC_VARS][4];
    char file[32], on[32], count[32], status[64], page[12];
    u32 list_page, popup, header, result;
    char row_text[RC_VISIBLE][5][32], restart[32], title[32];
};

static void rc_int(struct rc_ui *u,u32 i,u32 value)
{ ((fw3)0xC0593F30u)(0,(u32)(uintptr_t)u->names[i],value); }
static void rc_str(struct rc_ui *u,u32 i,const char *text)
{ ((fw3)0xC0593FE0u)(0,(u32)(uintptr_t)u->names[i],(u32)(uintptr_t)text); }

static u32 rc_mask(u8 *S)
{
    u32 cfg=SW(S,S_CFG),mask=0,n=W(cfg+CFG_NEN);
    u32 explicit_list=W(cfg+CFG_MAGIC)==OGC_CFG_MAGIC && W(cfg+CFG_VERSION)==OGC_CFG_VERSION &&
        W(cfg+CFG_SUM)==fnv(cfg,CFG_SUM) && n && n<=OGC_MAX_ROWS;
    for(u32 i=0;i<SW(S,S_NAVAIL);i++) {
        u32 lab=(u32)(uintptr_t)S+S_AVAIL+8u*i;
        if(explicit_list?enabled(S,lab):row_by_label(S,lab)>=0)mask|=1u<<i;
    }
    return mask;
}

static u32 rc_set(u8 *S,u32 index,u32 on)
{
    if(busy())return 4u;
    u32 n=SW(S,S_NAVAIL),labels[2*OGC_MAX_ROWS],count=0,mask=rc_mask(S);
    u32 capacity=OGC_MAX_ROWS-(SW(S,S_VRC)?1u:0u);
    if(index>=n)return 1u;
    u32 next=on?mask|(1u<<index):mask&~(1u<<index);
    if(next==mask)return 0;
    for(u32 i=0;i<n;i++)if(next&(1u<<i)) {
        if(count==capacity)return 3u;
        labels[2*count]=SW(S,S_AVAIL+8u*i);labels[2*count+1]=SW(S,S_AVAIL+8u*i+4u);count++;
    }
    /* NEN=0 means defaults in RCS1. VRC000 never names a disk row, so this
     * reserved label represents an explicit empty file list without migration. */
    if(!count){labels[0]=0x30435256u;labels[1]=0x00003030u;count=1;}
    u32 cfg=SW(S,S_CFG),before[CFG_BYTES/4u],dirty=SW(S,S_DIRTY);
    copy((u32)(uintptr_t)before,cfg,CFG_BYTES);
    if(!ogc_enable_set(S,count,(u32)(uintptr_t)labels))return 1u;
    if(ogc_save(S))return 0;
    copy(cfg,(u32)(uintptr_t)before,CFG_BYTES);SW(S,S_DIRTY)=dirty;return 5u;
}

/* A refresh has its own file object and one bounded file buffer. It never
 * overwrites a loaded RCD, live table, QS asset or virtual-RCD staging buffer. */
static u32 rc_refresh(u8 *S,struct rc_ui *u)
{
    if(busy())return 4u;
    u32 stage=((u32)(uintptr_t)(u+1)+63u)&~63u,fo=stage+S_BODY;
    u8 *T=(u8 *)(uintptr_t)stage;
    copy(stage,(u32)(uintptr_t)S,S_BODY);
    SW(T,S_FOBJ)=fo;SW(T,S_DATA)=fo+0x1000u;SW(T,S_DATA_CAP)=RCD_MAX_FILE;SW(T,S_DATA_USED)=0;
    u32 seen=0,n=list_rcd(T,(const char *)(uintptr_t)SW(S,S_PATH),&seen),count=0,labels[2*OGC_MAX_AVAIL];
    for(u32 i=0;i<n;i++) {
        u32 reason=0,f=read_rcd(T,fo+FO_NAMES+16u*i,W(fo+FO_SIZES+4u*i),&reason);
        if(!f||rcd_check(T,f,W(fo+FO_SIZES+4u*i)))continue;
        u32 duplicate=0;
        for(u32 j=0;j<count;j++)if(same_label(f+RH_LABEL,(u32)(uintptr_t)labels+8u*j))duplicate=1;
        if(duplicate)continue;
        labels[2*count]=W(f+RH_LABEL);labels[2*count+1]=W(f+RH_LABEL+4u);count++;
    }
    /* Preserve the selected filename when the sorted catalogue grows. */
    u32 lab[2]={0,0};
    if(u->index<SW(S,S_NAVAIL)){lab[0]=SW(S,S_AVAIL+8u*u->index);lab[1]=SW(S,S_AVAIL+8u*u->index+4u);}
    copy((u32)(uintptr_t)S+S_AVAIL,(u32)(uintptr_t)labels,8u*count);SW(S,S_NAVAIL)=count;
    u->index=0;
    for(u32 i=0;i<count;i++)if(same_label((u32)(uintptr_t)lab,(u32)(uintptr_t)labels+8u*i))u->index=i;
    return 0;
}

static u32 rc_num(char *p,u32 n)
{
    u32 k=0;if(n>=10u)p[k++]='0'+n/10u;p[k++]='0'+n%10u;p[k]=0;return k;
}

static void rc_words(char *to,u32 a,u32 b,u32 c,u32 d,u32 e,u32 f)
{
    volatile u32 *w=(volatile u32 *)to;w[0]=a;w[1]=b;w[2]=c;w[3]=d;w[4]=e;w[5]=f;w[6]=0;
}

static void rc_hint(struct rc_ui *u)
{
    if(u->result==3u)rc_words(u->status,0x7473694cu,0x6c756620u,0x64203a6cu,0x62617369u,0x6f20656cu,0x0000656eu);
    else if(u->result==6u)rc_words(u->status,0x74736552u,0x20747261u,0x61206f74u,0x796c7070u,0x00000000u,0x00000000u);
    else if(u->result==5u)rc_words(u->status,0x74697257u,0x61662065u,0x64656c69u,0x00000000u,0x00000000u,0x00000000u);
    else if(u->result==4u)rc_words(u->status,0x6f636552u,0x6e696472u,0x75622067u,0x00007973u,0x00000000u,0x00000000u);
    else if(u->popup)rc_words(u->status,0x203a4b4fu,0x666e6f63u,0x006d7269u,0x00000000u,0x00000000u,0x00000000u);
    else if(u->header)rc_words(u->status,0x5446454cu,0x4749522fu,0x203a5448u,0x65676170u,0x00000000u,0x00000000u);
    else rc_words(u->status,0x203a4b4fu,0x656c6573u,0x00007463u,0x00000000u,0x00000000u,0x00000000u);
    rc_str(u,RC_STATUS,u->status);rc_str(u,RC_RESTART,u->restart);
}

static void rc_post(struct rc_ui *u,u32 result)
{
    u8 *S=(u8 *)(uintptr_t)u->S;u32 mask=rc_mask(S),n=SW(S,S_NAVAIL),used=0;
    u->result=result;
    if(u->index>=n)u->index=n?n-1u:0;
    u32 pages=n?(n+RC_VISIBLE-1u)/RC_VISIBLE:1u;
    if(u->list_page>=pages)u->list_page=pages-1u;
    for(u32 i=0;i<sizeof(u->file);i++)u->file[i]=u->on[i]=u->count[i]=0;
    u->file[0]='R';u->file[1]='C';u->file[2]='D';u->file[3]=' ';
    if(n)copy((u32)(uintptr_t)u->file+4u,(u32)(uintptr_t)S+S_AVAIL+8u*u->index,8u);
    else {u->file[4]='N';u->file[5]='o';u->file[6]='n';u->file[7]='e';}
    if(n&&(mask&(1u<<u->index)))rc_words(u->on,0x62616e45u,0x2064656cu,0x00004e4fu,0x00000000u,0x00000000u,0x00000000u);
    else rc_words(u->on,0x62616e45u,0x2064656cu,0x0046464fu,0x00000000u,0x00000000u,0x00000000u);
    for(u32 i=0;i<n;i++)if(mask&(1u<<i))used++;
    u32 at=rc_num(u->count,used);u->count[at++]='/';rc_num(u->count+at,OGC_MAX_ROWS-(SW(S,S_VRC)?1u:0u));
    rc_str(u,RC_FILE,u->file);rc_str(u,RC_ON,u->on);rc_str(u,RC_COUNT,u->count);
    rc_words(u->title,0x2d534552u,0x54535543u,0x28204d4fu,0,0,0);
    at=12u+rc_num(u->title+12u,used);u->title[at++]='/';
    at+=rc_num(u->title+at,OGC_MAX_ROWS-(SW(S,S_VRC)?1u:0u));u->title[at++]=')';u->title[at]=0;
    rc_str(u,RC_TITLE,u->title);
    u32 width=pages==1u?1024u:pages==2u?512u:pages==3u?341u:256u;
    for(u32 k=0;k<RC_TABS;k++) {
        rc_int(u,RC_TAB+k,k<pages);rc_int(u,RC_TAB+RC_TABS+k,k==u->list_page);
        rc_int(u,RC_TAB+2u*RC_TABS+k,width*k);
        rc_int(u,RC_TAB+3u*RC_TABS+k,k+1u==pages?1024u-width*k:width);
    }
    for(u32 k=0;k<RC_VISIBLE;k++) {
        u32 index=u->list_page*RC_VISIBLE+k,valid=index<n,enabled_now=valid&&(mask&(1u<<index));
        u32 base=RC_ROWS+k*RC_PARTS;
        for(u32 j=0;j<5u;j++)for(u32 i=0;i<32u;i++)u->row_text[k][j][i]=0;
        if(valid) {
            char *name=u->row_text[k][enabled_now?RC_N:RC_G];
            copy((u32)(uintptr_t)name,(u32)(uintptr_t)S+S_AVAIL+8u*index,8u);
            u32 len=slen((u32)(uintptr_t)name);name[len++]='.';name[len++]='R';name[len++]='C';name[len]='D';
            if(enabled_now)rc_words(u->row_text[k][RC_E],0x62616e45u,0x0064656cu,0x00000000u,0x00000000u,0x00000000u,0x00000000u);
            else rc_words(u->row_text[k][RC_R],0x61736944u,0x64656c62u,0x00000000u,0x00000000u,0x00000000u,0x00000000u);
        } else if(!n&&!k) {
            rc_words(u->row_text[k][RC_N],0x52206f4eu,0x66204443u,0x73656c69u,0x00000000u,0x00000000u,0x00000000u);
        }
        for(u32 part=0;part<5u;part++)rc_str(u,base+part,u->row_text[k][part]);
        rc_int(u,base+RC_VIS,valid||(!n&&!k));rc_int(u,base+RC_LOCK,!valid);
        rc_int(u,base+RC_SELECTED,!enabled_now);rc_int(u,base+RC_MORE,0);
        rc_int(u,base+RC_DEFAULT,!enabled_now);rc_int(u,base+RC_VERSIONX,49u);
    }
    rc_hint(u);
}

/* Descriptors borrow the resident name, so every callback checks both its
 * exact variable slot and the consumer-owned context before changing state. */
static struct rc_ui *rc_owner(u32 desc,u32 variable)
{
    struct rc_ui *u=(struct rc_ui *)(uintptr_t)(W(desc+4u)-__builtin_offsetof(struct rc_ui,names)-16u*variable);
    if(u->magic!=0x32464352u||SW((u8 *)(uintptr_t)u->S,S_FILE_UI)!=(u32)(uintptr_t)u)return 0;
    return u;
}

static u32 rc_key(u32 desc)
{
    struct rc_ui *u=rc_owner(desc,RC_KEY);if(!u)return 0;
    u8 *S=(u8 *)(uintptr_t)u->S;u32 key=W(desc+8u),n=SW(S,S_NAVAIL);
    if(!key)return 0;
    if(key==10u||key==11u) {
        u32 last=n?(n-1u)/RC_VISIBLE:0;
        if(key==10u&&u->list_page)u->list_page--;
        if(key==11u&&u->list_page<last)u->list_page++;
        u->index=u->list_page*RC_VISIBLE;u->popup=0;rc_post(u,0);
    } else if(key>=20u&&key<=20u+RC_VISIBLE) {
        if(key>20u&&u->result==6u)u->result=0;
        u->popup=key-20u;
        if(u->popup)u->index=u->list_page*RC_VISIBLE+u->popup-1u;
        rc_hint(u);
    } else if(key==31u||key==30u) {
        u->header=key==31u;u->popup=0;rc_hint(u);
    }
    rc_int(u,RC_KEY,0);return 0;
}

static u32 rc_focus(u32 desc)
{
    struct rc_ui *u=rc_owner(desc,RC_FOCUS);if(!u)return 0;
    u->header=W(desc+8u)==3451u;rc_hint(u);return 0;
}

static u32 rc_choice(u32 desc,u32 row)
{
    u32 variable=RC_ROWS+(row-1u)*RC_PARTS+RC_CHOICE;
    struct rc_ui *u=rc_owner(desc,variable);if(!u)return 0;
    u32 choice=W(desc+8u);if(choice==255u)return 0;
    u8 *S=(u8 *)(uintptr_t)u->S;u32 index=u->list_page*RC_VISIBLE+row-1u;
    /* SupManager's right-to-More choice (2) has no file action. Only explicit
     * Enable/Disable choices act; a hidden row never aliases another file. */
    if(choice<=1u&&index<SW(S,S_NAVAIL)) {
        u32 before=rc_mask(S);
        u->index=index;u32 result=rc_set(S,index,choice==0u);
        rc_post(u,!result&&rc_mask(S)!=before?6u:result);
    }
    rc_int(u,variable,255u);return 0;
}
static u32 rc_choice1(u32 d){return rc_choice(d,1);}
static u32 rc_choice2(u32 d){return rc_choice(d,2);}
static u32 rc_choice3(u32 d){return rc_choice(d,3);}
static u32 rc_choice4(u32 d){return rc_choice(d,4);}
static u32 rc_choice5(u32 d){return rc_choice(d,5);}

static u32 ogc_files_init(u8 *S,u32 blob,u32 state)
{
    struct rc_ui *u=(struct rc_ui *)(uintptr_t)state;
    if(W(blob)!=0x32464352u||W(blob+4u)>RC_STRINGS||W(blob+32u)!=RC_VARS||W(blob+36u)!=20u)return 0;
    u->magic=0x32464352u;u->S=(u32)(uintptr_t)S;u->blob=blob;u->app=W(0xC37B7048u);
    if(!u->app||!uis_reader())return 0;
    const char *strings[RC_STRINGS];u32 offsets[RC_STRINGS],at=blob+W(blob+12u),n=W(blob+4u);
    for(u32 i=0;i<n;i++){strings[i]=(const char *)(uintptr_t)at;at+=slen(at)+1u;}
    if(uis_intern_many(strings,n,UIS_NOT_STOCK,offsets)!=UIS_OK)return 0;
    for(u32 i=0;i<W(blob+8u);i++) {
        u32 r=blob+W(blob+16u)+8u*i;
        put_be32(blob+W(blob+24u)+W(r),offsets[W(r+4u)]);
    }
    u->status[0]=' ';u->page[0]='R';u->page[1]='C';u->page[2]='_';u->page[3]='F';u->page[4]='I';u->page[5]='L';u->page[6]='E';u->page[7]='S';
    rc_words(u->restart,0x74736552u,0x20747261u,0x75206f74u,0x74616470u,0x00000065u,0x00000000u);
    for(u32 i=0;i<RC_VARS;i++) {
        u32 entry=blob+W(blob+20u)+20u*i,type=W(entry);
        copy((u32)(uintptr_t)u->names[i],entry+4u,16u);
        u32 d=0,reg=W(u->app+0x888u);
        if(!reg||((u32(*)(u32,u32,u32))0xC05DB419u)(reg+0x60u,(u32)(uintptr_t)u->names[i],(u32)(uintptr_t)&d)||d)return 0;
        u32 value=type==2u?(u32)(uintptr_t)u->status:i==RC_FOCUS?3451u:
            i>=RC_ROWS&&i<RC_TAB&&(i-RC_ROWS)%RC_PARTS==RC_CHOICE?255u:0;
        u32 def[3]={type,(u32)(uintptr_t)u->names[i],value};
        if(((u32(*)(u32,u32,u32))0xC05DB309u)(u->app,1,(u32)(uintptr_t)def))return 0;
    }
    SW(S,S_FILE_UI)=state;
    ((fw3)0xC0560FB0u)(0xC37B7048u,(u32)(uintptr_t)u->names[RC_KEY],(u32)(uintptr_t)&rc_key);
    ((fw3)0xC0560FB0u)(0xC37B7048u,(u32)(uintptr_t)u->names[RC_FOCUS],(u32)(uintptr_t)&rc_focus);
    ((fw3)0xC0560FB0u)(0xC37B7048u,(u32)(uintptr_t)u->names[RC_ROWS+0u*RC_PARTS+RC_CHOICE],(u32)(uintptr_t)&rc_choice1);
    ((fw3)0xC0560FB0u)(0xC37B7048u,(u32)(uintptr_t)u->names[RC_ROWS+1u*RC_PARTS+RC_CHOICE],(u32)(uintptr_t)&rc_choice2);
    ((fw3)0xC0560FB0u)(0xC37B7048u,(u32)(uintptr_t)u->names[RC_ROWS+2u*RC_PARTS+RC_CHOICE],(u32)(uintptr_t)&rc_choice3);
    ((fw3)0xC0560FB0u)(0xC37B7048u,(u32)(uintptr_t)u->names[RC_ROWS+3u*RC_PARTS+RC_CHOICE],(u32)(uintptr_t)&rc_choice4);
    ((fw3)0xC0560FB0u)(0xC37B7048u,(u32)(uintptr_t)u->names[RC_ROWS+4u*RC_PARTS+RC_CHOICE],(u32)(uintptr_t)&rc_choice5);
    rc_post(u,0);return 1;
}

static int ogc_files_button(void *ctx)
{
    u8 *S=(u8 *)ctx;struct rc_ui *u=(struct rc_ui *)(uintptr_t)SW(S,S_FILE_UI);
    if(!u||busy())return 4;
    u32 reader=uis_reader(),rd=0;
    if(!u->state) {
        if(W(u->app+0x80u)>=W(u->app+0x84u)||W(u->app+0xf8u)>=W(u->app+0xfcu))return 9;
        if(((u32(*)(u32,u32,u32,u32))0xC05E84D9u)(u->app,u->blob+W(u->blob+24u),W(u->blob+28u),(u32)(uintptr_t)&rd)||!rd)return 9;
        W(rd+0x10u)=W(reader+0x10u);W(rd+0x14u)=W(reader+0x14u);u->state=1;
    }
    u32 rc=rc_refresh(S,u);u->list_page=u->index/RC_VISIBLE;u->popup=0;u->header=1;rc_post(u,rc);if(rc)return rc;
    ((fw3)0xC0593F30u)(0,(u32)(uintptr_t)u->names[1],3451u);
    u32 gui=((fw0)0xC054DD38u)();if(!gui)return 9;
    if(!((fw2)W(W(gui)+12u))(gui,(u32)(uintptr_t)u->page))return 9;
    return ((u32(*)(u32,u32,u32,u32))0xC05DCB41u)(u->app,(u32)(uintptr_t)u->page,0,0)?9:0;
}
