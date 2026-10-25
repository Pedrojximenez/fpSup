/* Native Loader v4 touch/UI experiment. Values belong to this sup, never to
 * recording settings. The explicit TEST caption must stay until an actual
 * recording-service adapter supplies canonical values and legal options. */
#include <stdint.h>
#include "sloader4.h"
#include "fpsup_ui.c"
#include "private_core.c"

#define USED __attribute__((used))
#define TOUCH_SLOT 0xC0CFCCDCu
#define TOUCH_ORIGINAL 0xC05131A0u
#define TEST_MAGIC 0x31545351u
enum { V_TOUCH, V_ACTIVE, V_KEY, V_X, V_Y, V_FOCUS, V_FOOTER, V_STATUS, V_BG, V_SLOTS };
enum { V_INPUT = V_SLOTS + 8u * 4u };
enum { T_ROW, T_PAGE, T_HOME, T_CAPTION, T_WARNING, T_BLANK, T_NAMES, T_FORMAT=10,
       T_DC=15, T_RES=19, T_FPS=24, T_MORE=30 };
struct config { uint32_t magic, state_off, ui_off, ui_len; };
struct touch_sup {
    uint32_t magic, result, installed, packets, consumed, cancelled, applied;
    const struct sl_svc *svc;
    const void *ui;
    struct sl_row row;
    QtState q;
    QttState touch;
    volatile uint32_t active;
    uint32_t raw_owned, raw_contacts, serial, detail, epoch;
    uint32_t rendered, render_rev, render_detail, focus_slot, focus_on;
    int16_t raw_x, raw_y;
};
_Static_assert(sizeof(struct touch_sup)<=4096u,"SUP state exceeds its owned BSS");

__asm__(".text\n.balign 4\nqst_context:\n.word 0\n");
extern const uint32_t qst_context;
static struct touch_sup *context(void) { return (struct touch_sup *)(uintptr_t)qst_context; }
static uint32_t ms(void) { return ((uint32_t (*)(void))0xC002B920u)(); }
static int coord(int32_t x, int32_t y) { return x>=0 && x<1024 && y>=0 && y<682; }
static unsigned count_options(unsigned tile) { return tile==QT_FORMAT?5u:tile==QT_FPS?6u:tile==QT_DC?4u:5u; }
static unsigned option_base(unsigned tile) { return tile==QT_FORMAT?T_FORMAT:tile==QT_DC?T_DC:tile==QT_RES?T_RES:T_FPS; }
static const char *text(struct touch_sup *s, unsigned i) { return fpui_text(s->ui,i); }

/* Keep the proven queued screen-manager path. Direct app switching was an
 * unsuccessful hardware diagnostic; the page now retains native focus. */
static int show_page(const char *name) {
    return fpui_show(name);
}

static void render(struct touch_sup *s) {
    QtState *q=&s->q;QttState *t=&s->touch;
    unsigned slot=t->active && t->gesture==DRAG?t->target_slot:q->focus;
    int tile=qt_for_native(q->slots[q->focus]);
    unsigned focus_on=!s->detail && t->open && qt_for_native(q->slots[slot])>=0;
    if(!s->rendered || s->focus_slot!=slot || s->focus_on!=focus_on) {
        fpui_set(s->ui,V_X,slot%4u*256u);fpui_set(s->ui,V_Y,slot<4u?77u:308u);
        fpui_set(s->ui,V_FOCUS,focus_on);s->focus_slot=slot;s->focus_on=focus_on;
    }
    /* MOVE samples that leave the visible state unchanged do not republish
     * the whole page or add work to the native GUI queue. */
    if(s->rendered && s->render_rev==q->revision && s->render_detail==s->detail)return;
    s->rendered=1;s->render_rev=q->revision;s->render_detail=s->detail;
    fpui_set_text(s->ui,V_STATUS,text(s,s->detail?T_MORE+s->detail-1u:T_CAPTION));
    fpui_set_text(s->ui,V_FOOTER,tile<0?text(s,T_WARNING):q->tiles[tile].text);
    for(unsigned k=0;k<8u;k++) {
        int id=qt_for_native(q->slots[k]);
        unsigned v=V_SLOTS+4u*k;
        int visible=s->detail?k<count_options(s->detail-1u):id>=0;
        fpui_set(s->ui,v+3u,visible);
        fpui_set_text(s->ui,v,text(s,s->detail?T_NAMES+s->detail-1u:id>=0?T_NAMES+(unsigned)id:T_BLANK));
        fpui_set_text(s->ui,v+1u,s->detail && visible?text(s,option_base(s->detail-1u)+k):
                                      id>=0?q->tiles[id].text:text(s,T_BLANK));
        fpui_set_text(s->ui,v+2u,text(s,T_WARNING));
    }
}
static void close_page(struct touch_sup *s) {
    __atomic_store_n(&s->active,0,__ATOMIC_RELEASE);s->detail=0;s->touch.open=0;
    s->result=show_page(text(s,T_HOME));
}
static void choose(struct touch_sup *s,unsigned tile,unsigned index) {
    if(tile>=QT_COUNT || index>=count_options(tile))return;
    /* This is the test model's canonical feedback, not a firmware setter. */
    if(qt_configure(&s->q,tile,count_options(tile),index,text(s,option_base(tile)+index),text(s,T_WARNING)))
        ++s->applied;
}
static uint32_t active_changed(uintptr_t desc) {
    struct touch_sup *s=context();if(!s || s->magic!=TEST_MAGIC)return 0;
    __atomic_store_n(&s->active,fpui_value(desc)==1u,__ATOMIC_RELEASE);
    if(!s->active){s->touch.active=0;s->touch.open=0;s->detail=0;}
    return 0;
}
static uint32_t touch_changed(uintptr_t desc) {
    struct touch_sup *s=context();if(!s || !s->active || s->magic!=TEST_MAGIC)return 0;
    uint32_t word=fpui_value(desc),phase=(word>>20)&3u,now=ms();
    if(((word>>22)&511u)!=(s->epoch&511u))return 0; /* queued from an older page opening */
    QttEvent e={(QttPhase)phase,(int16_t)(word&1023u),(int16_t)((word>>10)&1023u),now,1,
                phase==QTT_DOWN || phase==QTT_MOVE?1u:0u};
    unsigned was_detail=s->detail;
    /* A held contact can start reordering before its first moved sample. */
    qtt_tick(&s->touch,&s->q,now);
    QttResult r=qtt_event(&s->touch,&s->q,e);
    if(r.flags&QTT_SET)choose(s,r.intent.tile,r.intent.index);
    if(r.flags&QTT_MORE) {s->detail=r.intent.tile+1u;qtt_more_view(&s->touch,1);}
    if(r.flags&QTT_BACK)s->detail=0;
    if(phase==QTT_UP && !(r.flags&QTT_BACK) && !s->touch.moved) {
        if(e.y<77 && e.x>=896){close_page(s);return 0;}
        if(was_detail && s->detail && e.y>=77 && e.y<531) {
            unsigned k=e.x/256u+(e.y>=308?4u:0u);
            if(e.y<300 || e.y>=308)choose(s,was_detail-1u,k);
        }
    }
    if(r.flags&QTT_CLOSE){close_page(s);return 0;}
    render(s);return 0;
}
static int open_page(void *arg) {
    struct touch_sup *s=arg;
    if(!s || !s->installed)return SL_BADARG;
    qtt_init(&s->touch);s->touch.open=1;++s->epoch;s->detail=0;
    __atomic_store_n(&s->active,1,__ATOMIC_RELEASE);
    render(s);s->result=show_page(text(s,T_PAGE));
    if(s->result)__atomic_store_n(&s->active,0,__ATOMIC_RELEASE);
    return (int)s->result;
}

/* XC_TouchPanelData reaching the existing TouchOperationObserver has six
 * words: x/y, second x/y, timestamp, mapped gesture. Contact identity comes
 * from valid coordinates, not from guessing the mapped gesture's flags.
 * The observer runs off the GUI thread. Only POST_INT is used here; all model
 * and page operations happen after the page relays this silent update into
 * QST_Input with a notifying native controlAppVariable action. */
USED static uint32_t touch_observer(uintptr_t observer,const int32_t *data) {
    struct touch_sup *s=context();
    if(!s || !s->installed || !data)return ((uint32_t (*)(uintptr_t,const int32_t *))TOUCH_ORIGINAL)(observer,data);
    unsigned n=coord(data[0],data[1])?1u:0u;
    if(n && coord(data[2],data[3]))n=2;
    unsigned prev=s->raw_contacts;s->raw_contacts=n;
    if(!prev && n) s->raw_owned=__atomic_load_n(&s->active,__ATOMIC_ACQUIRE)!=0;
    if(!s->raw_owned)return ((uint32_t (*)(uintptr_t,const int32_t *))TOUCH_ORIGINAL)(observer,data);
    ++s->packets;
    if(n){s->raw_x=(int16_t)data[0];s->raw_y=(int16_t)data[1];}
    if(__atomic_load_n(&s->active,__ATOMIC_ACQUIRE)) {
        unsigned phase=n>1 || prev>1?QTT_CANCEL:!n?QTT_UP:!prev?QTT_DOWN:QTT_MOVE;
        uint32_t packed=((++s->serial&1u)<<31)|((s->epoch&511u)<<22)|(phase<<20)|
                        ((uint32_t)s->raw_y<<10)|(uint32_t)s->raw_x;
        fpui_set(s->ui,V_TOUCH,packed);
        if(phase==QTT_CANCEL)++s->cancelled;
    }
    ++s->consumed;
    if(!n)s->raw_owned=0;
    return 1;
}

USED int sup_entry(void *block,const struct sl_svc *svc,const char *path) {
    (void)path;
    const struct config *cfg=(const struct config *)((uintptr_t)block+48u);
    if(!svc || svc->version<6u || cfg->magic!=TEST_MAGIC || (uintptr_t)block<SL_ALIAS)return SL_RELEASE;
    if(fpui_rd(TOUCH_SLOT)!=TOUCH_ORIGINAL)return SL_RELEASE;
    if(svc->claim(svc,TOUCH_SLOT,4u,&(const uint32_t){TOUCH_ORIGINAL},SL_EXCL)!=SL_OK)return SL_RELEASE;
    struct touch_sup *s=(struct touch_sup *)((uintptr_t)block+cfg->state_off);
    s->magic=TEST_MAGIC;s->svc=svc;s->ui=(const void *)((uintptr_t)block+cfg->ui_off);
    *(volatile uint32_t *)(uintptr_t)&qst_context=(uint32_t)(uintptr_t)s;
    s->result=fpui_install(svc,s->ui);
    /* Registration may borrow pointers before failing: retain the block. */
    if(s->result)return SL_KEEP;
    uint8_t layout[8]={20,17,21,22,0,0,0,0};qt_init(&s->q,layout);
    for(unsigned i=0;i<QT_COUNT;i++)choose(s,i,0);
    qt_start(&s->q);qtt_init(&s->touch);
    fpui_watch(s->ui,V_INPUT,touch_changed);fpui_watch(s->ui,V_ACTIVE,active_changed);
    s->row.kind=SL_ROW_JUMP;s->row.title=text(s,T_ROW);s->row.value=text(s,T_WARNING);
    s->row.open=open_page;s->row.arg=s;
    if(svc->page_add(svc,&s->row)<0){s->result=20;return SL_KEEP;}
    s->installed=1;
    svc->publish(svc);                         /* code, context and pages first */
    fpui_wr(TOUCH_SLOT,(uint32_t)(uintptr_t)touch_observer);
    svc->publish(svc);                         /* arm last; journal restores it */
    return SL_KEEP;
}
