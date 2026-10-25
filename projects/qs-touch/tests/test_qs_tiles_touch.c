#include "../core/qs_tiles_touch.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint32_t now = 10;
static QttResult event(QttState *t, QtState *q, QttPhase phase, int x, int y) {
    now += 20;
    return qtt_event(t,q,(QttEvent){phase,(int16_t)x,(int16_t)y,now,1,(uint8_t)(phase == QTT_UP || phase == QTT_CANCEL ? 0 : 1)});
}
static QttResult tap(QttState *t, QtState *q, int x, int y) {
    event(t,q,QTT_DOWN,x,y); return event(t,q,QTT_UP,x,y);
}
static void setup(QttState *t, QtState *q) {
    uint8_t ids[] = {20,17,21,22,25,8,1,48};
    assert(qt_init(q,ids));
    for (unsigned i=0;i<QT_COUNT;++i) assert(qt_configure(q,i,5,1,"value","detail"));
    assert(qt_start(q)); qtt_init(t);
}
static void integer(void *ctx,const char *key,uint32_t value) {
    QttState *t=ctx;
    assert(t->publishing && !qtt_toggle(t).flags);
    printf("I %s %u\n",key,value);
}
static void text(void *ctx,const char *key,const char *value) { (void)ctx;printf("T %s %s\n",key,value); }

int main(void) {
    QtState q; QttState t; setup(&t,&q);
    assert(!event(&t,&q,QTT_DOWN,400,300).consumed); /* ordinary LV untouched */
    assert(event(&t,&q,QTT_DOWN,400,10).consumed);
    event(&t,&q,QTT_MOVE,400,210); assert(t.open==0); /* no intermediate reveal */
    QttResult r=event(&t,&q,QTT_UP,400,210);assert(r.flags==QTT_OPEN && t.open==1);
    r=tap(&t,&q,350,150);assert(r.flags==QTT_SELECT && q.focus==1);
    r=tap(&t,&q,350,150);assert((r.flags&(QTT_SELECT|QTT_MORE))==(QTT_SELECT|QTT_MORE));
    assert(r.intent.tile==QT_DC && r.intent.action==QT_MORE);
    assert(event(&t,&q,QTT_UP,350,150).flags==0); /* duplicate release cannot repeat */
    r=tap(&t,&q,830,645);assert(r.flags==QTT_SET && r.intent.index==2);
    assert(q.tiles[QT_DC].index==1); /* no optimistic camera value */
    event(&t,&q,QTT_DOWN,600,645);event(&t,&q,QTT_MOVE,350,645);
    assert(t.draft==4 && q.tiles[QT_DC].index==1);
    r=event(&t,&q,QTT_CANCEL,350,645);assert(!r.flags && q.tiles[QT_DC].index==1);
    event(&t,&q,QTT_DOWN,600,645);r=event(&t,&q,QTT_UP,350,645);
    assert(r.flags==QTT_SET && r.intent.tile==QT_DC && r.intent.index==4);
    event(&t,&q,QTT_DOWN,600,645);r=event(&t,&q,QTT_UP,600,570);
    assert(r.flags==QTT_CLOSE && !t.open); /* footer upward swipe */
    qtt_toggle(&t);r=tap(&t,&q,950,645);assert(r.flags==QTT_MORE);
    assert(qtt_more_view(&t,1));
    event(&t,&q,QTT_DOWN,500,640);r=event(&t,&q,QTT_UP,500,510);
    assert(r.flags==QTT_BACK && t.open && !t.more_view);
    /* Select a native-only tile: its footer is handed off for the entire contact. */
    r=tap(&t,&q,100,350);assert(r.flags==QTT_SELECT && q.focus==4);
    assert(!event(&t,&q,QTT_DOWN,500,645).consumed);
    assert(!event(&t,&q,QTT_UP,500,645).consumed);
    /* Two contacts cancel and drain through the final release. */
    event(&t,&q,QTT_DOWN,350,150);
    r=qtt_event(&t,&q,(QttEvent){QTT_MOVE,350,150,now+1,2,2});assert(r.consumed && !r.flags);
    assert(event(&t,&q,QTT_UP,350,150).flags==0 && !t.blocked);
    assert(q.focus==4);
    /* Feedback/focus revision during a drag invalidates it. */
    tap(&t,&q,350,150);event(&t,&q,QTT_DOWN,600,645);
    assert(qt_configure(&q,QT_DC,4,1,"new","new"));
    assert(event(&t,&q,QTT_UP,300,645).flags==0);
    /* Reorder only commits on release, no interpolated/animated layout writes. */
    uint8_t old[8];memcpy(old,q.slots,8);
    event(&t,&q,QTT_DOWN,100,150);qtt_tick(&t,&q,now+480);
    event(&t,&q,QTT_MOVE,620,150);assert(!memcmp(old,q.slots,8));
    r=event(&t,&q,QTT_UP,620,150);assert(r.flags==QTT_REORDER && q.slots[2]==20 && q.focus==2);
    event(&t,&q,QTT_DOWN,620,150);qtt_tick(&t,&q,now+480);
    event(&t,&q,QTT_MOVE,100,150);memcpy(old,q.slots,8);
    event(&t,&q,QTT_CANCEL,100,150);assert(!memcmp(old,q.slots,8));
    /* Gap between native rows is not a tile. */
    r=tap(&t,&q,100,303);assert(!r.flags);
    assert(qtt_pages(&t,2));
    event(&t,&q,QTT_DOWN,900,150);r=event(&t,&q,QTT_UP,500,150);
    assert(r.flags==QTT_PAGE && r.page==1 && t.page_pending);
    assert(!qtt_page_ready(&t,&q));
    assert(!tap(&t,&q,100,150).flags); /* no stale page selection */
    assert(qt_layout(&q,old) && qtt_page_ready(&t,&q));
    assert(!t.page_pending && t.open);
    /* Two-finger drain must not reopen a closed panel. */
    qtt_toggle(&t);event(&t,&q,QTT_DOWN,500,10);
    qtt_event(&t,&q,(QttEvent){QTT_MOVE,500,200,now+1,2,2});
    assert(!event(&t,&q,QTT_UP,500,220).flags && !t.open);
    /* Sparse UP movement is not a long press, even after 480ms. */
    qtt_toggle(&t);event(&t,&q,QTT_DOWN,100,150);now+=600;
    r=event(&t,&q,QTT_UP,600,150);assert(!(r.flags&QTT_REORDER));
    if(t.page_pending) { assert(qt_layout(&q,old));assert(qtt_page_ready(&t,&q)); }
    tap(&t,&q,100,150);
    QtSink sink={&t,integer,text};assert(qtt_publish(&t,&q,&sink));assert(!t.publishing);
    puts("PASS normalized touch: snap open/close, select, double tap, step/drag, more/back, cancel, multi-contact, reorder, page readiness");
    return 0;
}
