/* Genuine QS_CINE adapter. No separate page and no demonstration settings. */
#include <stdint.h>
#include "sloader4.h"
#include "fpsup_ui.c"
#include "settings.h"
#include "qs_apply.c"
#include "qs_layer.c"

#define QSN_MAGIC 0x314E5351u
#define QSN_DATA 0x444E5351u
#define TOUCH_SLOT 0xC0CFCCDCu
#define TOUCH_STOCK 0xC05131A0u
#define USED __attribute__((used))
struct config {uint32_t magic,state,data,bytes,layer;};
struct data_header {uint32_t magic,bytes,np,patches,nv,vars,nr,refs,nn,names,nl,labels;};
struct var {uint32_t type,name,first,role,arg;};
struct patch {uint32_t addr,old_len,hash,out,len,n;};
struct native_qs {
    uint32_t magic,result,installed,packets,consumed,applied,epoch,serial;
    uintptr_t block,data,layer;
    const struct sl_svc *svc;
    struct qsn_native native;
    volatile uint32_t active;
    uint32_t contacts,owned;
    int32_t x,y,down_x,down_y;
    uint32_t down,moved,painting;
    uint32_t values[4],counts[4],slots[8],focus;
    char text[4][40];
};
_Static_assert(sizeof(struct native_qs)<4096,"QS state exceeds its block");
__asm__(".text\n.balign 4\nqsn_context:\n.word 0\n");
extern const uint32_t qsn_context;
static struct native_qs *qsn(void){return (struct native_qs *)(uintptr_t)qsn_context;}
static struct data_header *dh(struct native_qs *s){return (struct data_header *)s->data;}
static const char *label(struct native_qs *s,unsigned i){return (const char *)(s->data+peek(s->data+dh(s)->labels+4u*i));}
static const char *native_name(struct native_qs *s,unsigned i){return (const char *)(s->data+peek(s->data+dh(s)->names+4u*i));}
static struct var *vars(struct native_qs *s){return (struct var *)(s->data+dh(s)->vars);}
static int equal(const char *a,const char *b){while(*a && *a==*b){a++;b++;}return *a==*b;}
static void integer(struct native_qs *s,unsigned k,uint32_t v){
    ((fpui_fn3)FPUI_POST_INT)(0,s->data+vars(s)[k].name,v);
}
static void string(struct native_qs *s,unsigned k,const char *v){
    ((fpui_fn3)FPUI_POST_STR)(0,s->data+vars(s)[k].name,(uint32_t)(uintptr_t)v);
}
static unsigned role_index(struct native_qs *s,unsigned role){
    for(unsigned k=0;k<dh(s)->nv;k++)if(vars(s)[k].role==role)return k;
    return dh(s)->nv;
}
static int tile(unsigned id){return id==20?0:id==17?1:id==21?2:id==22?3:-1;}
static void number(char *to,unsigned value){
    char reverse[10];unsigned n=0;do{reverse[n++]=(char)('0'+value%10u);value/=10u;}while(value);
    while(n)*to++=reverse[--n];*to=0;
}
static void caption(struct native_qs *s,unsigned id,unsigned value){
    const char *p=0;unsigned k;
    if(id==0 && value<2)p=label(s,value);
    if(id==1 && value<2)p=label(s,2u+value);
    if(id==2 && value<2)p=label(s,4u+value);
    if(id==3 && value<9)p=label(s,6u+value);
    if(p){for(k=0;k<39u && p[k];k++)s->text[id][k]=p[k];s->text[id][k]=0;return;}
    p=label(s,id==2?15u:16u);for(k=0;k<24u && p[k];k++)s->text[id][k]=p[k];
    s->text[id][k++]=' ';number(s->text[id]+k,value);
}
static void paint(struct native_qs *s){
    if(!s->active || s->painting)return;s->painting=1;
    unsigned ready=1,focus=0;
    for(unsigned k=0;k<4;k++)ready &= qsn_read(&s->native,native_name(s,k),&s->values[k]);
    ready &= qsn_read(&s->native,native_name(s,6),&focus);
    for(unsigned k=0;k<8;k++)ready &= qsn_read(&s->native,native_name(s,7u+k),&s->slots[k]);
    s->focus=focus<8?focus:0;
    s->counts[0]=2;s->counts[1]=2;s->counts[2]=qs_rows_now();s->counts[3]=9;
    if(!s->counts[2] || s->counts[2]>64)ready=0;
    for(unsigned k=0;k<4;k++){
        if(s->values[k]>=64)ready=0;
        if(s->counts[k]<=s->values[k])s->counts[k]=s->values[k]+1u;
        caption(s,k,s->values[k]);
    }
    int selected=ready?tile(s->slots[s->focus]):-1;
    struct var *v=vars(s);
    for(unsigned k=0;k<dh(s)->nv;k++){
        unsigned a=v[k].arg,slot=a&7u,id=a>>3;
        switch(v[k].role){
        case 1:integer(s,k,!ready || tile(s->slots[a])<0);break;
        case 2:integer(s,k,ready && tile(s->slots[slot])==(int)id);break;
        case 3:integer(s,k,s->values[a]);break;
        case 4:integer(s,k,s->counts[a]?s->counts[a]-1u:0);break;
        case 5:string(s,k,s->text[a]);break;
        case 6:string(s,k,label(s,17));break;
        case 7:integer(s,k,selected<0);break;
        case 8:integer(s,k,selected>=0);break;
        case 9:string(s,k,selected<0?label(s,17):s->text[selected]);break;
        }
    }
    s->painting=0;
}
static uint32_t changed(uintptr_t d){(void)d;struct native_qs *s=qsn();if(s && s->magic==QSN_MAGIC)paint(s);return 0;}
static uint32_t active(uintptr_t d){
    struct native_qs *s=qsn();if(!s || s->magic!=QSN_MAGIC)return 0;
    s->active=fpui_value(d)==1u;s->epoch++;s->down=0;paint(s);return 0;
}
static uint32_t input(uintptr_t d){
    struct native_qs *s=qsn();if(!s || !s->active || s->magic!=QSN_MAGIC)return 0;
    uint32_t word=fpui_value(d),phase=(word>>20)&3u;
    if(((word>>22)&511u)!=(s->epoch&511u))return 0;
    int x=word&1023u,y=(word>>10)&1023u;
    if(phase==0){s->down=1;s->moved=0;s->down_x=x;s->down_y=y;return 0;}
    if(phase==3){s->down=0;return 0;}
    if(!s->down)return 0;
    int dx=x-s->down_x,dy=y-s->down_y;
    if(dx>16 || dx< -16 || dy>16 || dy< -16)s->moved=1;
    if(phase!=2)return 0;s->down=0;
    if(dy< -80){unsigned k=role_index(s,14);if(k<dh(s)->nv)integer(s,k,++s->serial);return 0;}
    uint32_t back=0;
    if(!s->moved && y>=77 && y<531 && (y<300 || y>=308)){
        unsigned slot=(unsigned)x/256u+(y>=308?4u:0u);
        qsn_apply(&s->native,native_name(s,6),slot,8u,&back);paint(s);return 0;
    }
    if(s->down_y>=608 && y>=608){
        paint(s);int id=tile(s->slots[s->focus]);
        int delta=s->moved?(dx>60?1:dx< -60?-1:0):x<128?-1:x>=768?1:0;
        if(id>=0 && delta){
            int target=(int)s->values[id]+delta;
            if(target>=0 && qsn_apply(&s->native,native_name(s,(unsigned)id),
                                     (unsigned)target,s->counts[id],&back))s->applied++;
            paint(s);
        }
    }
    return 0;
}
static int valid_xy(int x,int y){return x>=0 && x<1024 && y>=0 && y<682;}
USED static uint32_t observer(uintptr_t object,const int32_t *data){
    struct native_qs *s=qsn();
    if(!s || !s->installed || !data)return ((uint32_t (*)(uintptr_t,const int32_t *))TOUCH_STOCK)(object,data);
    unsigned n=valid_xy(data[0],data[1])?1u:0u;if(n && valid_xy(data[2],data[3]))n=2;
    unsigned previous=s->contacts;s->contacts=n;
    if(!previous && n)s->owned=s->active!=0;
    if(!s->owned)return ((uint32_t (*)(uintptr_t,const int32_t *))TOUCH_STOCK)(object,data);
    s->packets++;s->consumed++;
    if(n){s->x=data[0];s->y=data[1];}
    if(s->active){
        unsigned phase=n>1 || previous>1?3u:!n?2u:!previous?0u:1u;
        uint32_t value=((++s->serial&1u)<<31)|((s->epoch&511u)<<22)|(phase<<20)|((unsigned)s->y<<10)|(unsigned)s->x;
        unsigned k=role_index(s,11);if(k<dh(s)->nv)integer(s,k,value);
    }
    if(!n)s->owned=0;
    return 1;
}

/* Sparse replacement preserves the original stream coordinates seen by
 * Res-Custom. Its native parse is called once per replacement record. */
USED static uint32_t native_record(uintptr_t reader,uintptr_t header){
    struct native_qs *s=qsn();uintptr_t next=peek(header+QS_H_NEXT);
    if(!next)next=peek(header+QS_H_REPLAY);
    if(!s || !s->installed || peek(reader+36)!=QS_NBU_BASE)return ((fn1)next)(reader);
    uint32_t pos=peek(reader+4),source=QS_NBU_BASE+pos;
    struct patch *p=(struct patch *)(s->data+dh(s)->patches);
    for(unsigned k=0;k<dh(s)->np;k++)if(p[k].addr==source){
        if(rec_be32(source+4)!=p[k].old_len || qs_fnv(source,p[k].old_len)!=p[k].hash)
            return ((fn1)next)(reader);
        uint32_t result=0,at=0;
        for(unsigned j=0;j<p[k].n;j++){
            uint32_t record=s->data+p[k].out+at,n=rec_be32(record+4);
            if(n<8 || at+n>p[k].len)return ((fn1)next)(reader);
            poke(reader+36,record-pos);poke(reader+4,pos);
            result=((fn1)next)(reader);at+=n;
        }
        poke(reader+36,QS_NBU_BASE);poke(reader+4,pos+p[k].old_len);return result;
    }
    return ((fn1)next)(reader);
}

USED int sup_entry(void *block,const struct sl_svc *svc,const char *path){
    const struct config *c=(const struct config *)((uintptr_t)block+48u);
    if(!svc || svc->version<6 || c->magic!=QSN_MAGIC || (uintptr_t)block<SL_ALIAS)return SL_RELEASE;
    if(fpui_rd(TOUCH_SLOT)!=TOUCH_STOCK)return SL_RELEASE;
    uintptr_t data=(uintptr_t)block+c->data,header=(uintptr_t)block+c->layer;
    const struct data_header *d=(const struct data_header *)data;
    if(d->magic!=QSN_DATA || d->bytes!=c->bytes || d->np>256 || d->nv>128 || d->nn!=15)return SL_RELEASE;
    const struct patch *p=(const struct patch *)(data+d->patches);
    for(unsigned k=0;k<d->np;k++){
        if(p[k].out+p[k].len>d->bytes || p[k].n>512 || p[k].old_len<8 ||
           rec_be32(p[k].addr+4)!=p[k].old_len || qs_fnv(p[k].addr,p[k].old_len)!=p[k].hash)return SL_RELEASE;
        unsigned at=0;for(unsigned j=0;j<p[k].n;j++){
            unsigned n=rec_be32(data+p[k].out+at+4);if(n<8 || at+n>p[k].len)return SL_RELEASE;at+=n;
        }
        if(at!=p[k].len)return SL_RELEASE;
    }
    uintptr_t sites[2]={QS_SITE,QS_LAY_SITE};uint32_t stock[2]={QS_SITE_STOCK,QS_LAY_STOCK};
    for(unsigned k=0;k<2;k++){
        if(peek(sites[k])!=stock[k] && !svc->holder(svc,sites[k],0))return SL_RELEASE;
        if(svc->claim(svc,sites[k],4,&stock[k],SL_CHAIN)!=SL_OK)return SL_RELEASE;
    }
    if(svc->claim(svc,TOUCH_SLOT,4,&(const uint32_t){TOUCH_STOCK},SL_EXCL)!=SL_OK)return SL_RELEASE;
    uintptr_t veneer=svc->cave_alloc(svc,16);if(!veneer)return SL_RELEASE;
    struct native_qs *s=(struct native_qs *)((uintptr_t)block+c->state);
    s->magic=QSN_MAGIC;s->block=(uintptr_t)block;s->data=data;s->layer=header;s->svc=svc;
    s->native.app=fpui_rd(FPUI_GUI_OBJECT);s->native.lookup=(void *)0xC05DCA89u;s->native.notify=(void *)0xC05DC7C9u;
    if(!s->native.app)return SL_RELEASE;
    *(volatile uint32_t *)(uintptr_t)&qsn_context=(uint32_t)(uintptr_t)s;
    if(svc->borrow(svc,block,(const uint8_t *)block+((const struct sl4_header *)block)->block_size)!=SL_OK)return SL_KEEP;
    for(unsigned k=0;k<d->nr;k++){
        uint32_t at=peek(data+d->refs+8u*k),text=peek(data+d->refs+8u*k+4u);
        if(at+4>d->bytes || text>=d->bytes){s->result=1;return SL_KEEP;}
        /* Private aliases follow Loader v4's fixed string rule. */
        uint32_t id=(uint32_t)(data+text-SL_ALIAS);
        poke8(data+at,id>>24);poke8(data+at+1,id>>16);poke8(data+at+2,id>>8);poke8(data+at+3,id);
    }
    struct var *v=vars(s);
    for(unsigned k=0;k<d->nv;k++){
        uint32_t definition[3]={v[k].type,(uint32_t)(data+v[k].name),v[k].type==2?(uint32_t)(data+v[k].first):v[k].first};
        if(FPUI_FW(FPUI_VAR_REGISTER,fpui_fn3)(s->native.app,1,(uint32_t)(uintptr_t)definition)){s->result=2;return SL_KEEP;}
        uint32_t (*callback)(uintptr_t)=v[k].role==10?active:v[k].role==12?input:v[k].role==13?changed:0;
        if(callback)FPUI_FW(FPUI_VAR_WATCH,fpui_fn3)(FPUI_GUI_OBJECT,definition[1],(uint32_t)(uintptr_t)callback);
    }
    uint32_t name[2];name_of((uintptr_t)path,name);poke(header,name[0]);poke(header+4,name[1]);
    poke(header+QS_H_VERSION,QS_LAYER_VERSION);poke(header+QS_H_SVC,(uintptr_t)svc);
    poke(header+QS_H_NEXT,svc->chain_next(svc,QS_SITE,1));poke(header+QS_H_LAY_NEXT,svc->chain_next(svc,QS_LAY_SITE,1));
    poke(header+QS_H_REPLAY,header+QS_REPLAY_RECORD+1);poke(header+QS_H_LAY_REPLAY,header+QS_REPLAY_LAYOUT+1);
    poke(header+QS_H_RECORD,(uintptr_t)native_record);poke(header+QS_H_LAYOUT,(uintptr_t)qs_layout);
    poke(header+QS_H_STATE,QS_READY);
    poke(veneer,THUMB_VENEER);poke(veneer+4,header+QS_ENTRY_RECORD);
    poke(veneer+8,THUMB_VENEER);poke(veneer+12,header+QS_ENTRY_LAYOUT);
    s->installed=1;svc->publish(svc);
    poke(QS_SITE,bw_word(QS_SITE,veneer));poke(QS_LAY_SITE,bw_word(QS_LAY_SITE,veneer+8));
    fpui_wr(TOUCH_SLOT,(uintptr_t)observer);svc->publish(svc);return SL_KEEP;
}
