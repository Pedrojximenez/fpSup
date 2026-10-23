#include "../core/qs_touch.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void event(QsTouch *q, QsEventType type, int x, int y, uint32_t ms) {
    assert(qs_event(q, (QsEvent){type, (int16_t)x, (int16_t)y, ms, 1}));
}
static void down(QsTouch *q, int x, int y, uint32_t ms) { event(q, QS_DOWN, x, y, ms); }
static void up(QsTouch *q, int x, int y, uint32_t ms) { event(q, QS_UP, x, y, ms); }
int main(void) {
    QsTouch q; qs_init(&q);
    assert(sizeof(QsTouch) < 256);
    assert(!qs_event(&q, (QsEvent){QS_DOWN, 500, 300, 0, 1}));
    down(&q, 500, 8, 0); event(&q, QS_MOVE, 500, 80, 10); up(&q, 500, 80, 20);
    assert(q.mode == QS_CLOSED); /* short pull returns, no focus/camera intent */
    down(&q, 500, 8, 100); event(&q, QS_MOVE, 500, 300, 200); up(&q, 500, 300, 220);
    assert(q.mode == QS_OPEN && q.reveal == QS_HEIGHT);
    down(&q, 100, 180, 300); up(&q, 100, 180, 350);
    assert(qs_take_intent(&q) == 0 && qs_take_intent(&q) == -1);
    down(&q, 100, 180, 400); qs_tick(&q, 879); assert(q.mode == QS_OPEN);
    qs_tick(&q, 880); assert(q.mode == QS_EDIT && q.editing);
    event(&q, QS_MOVE, 600, 180, 900); up(&q, 600, 180, 920);
    assert(q.layout.ids[2] == 0 && q.layout.ids[0] == 1);
    assert(qs_take_intent(&q) == -1); /* long press never modifies a setting */
    qs_catalog(&q); assert(q.mode == QS_CATALOG);
    assert(!qs_add(&q, 0) && !qs_add(&q, 255));
    assert(qs_add(&q, 8) && q.layout.count == 9 && q.page == 1);
    assert(qs_finish_edit(&q, 1) && q.layout.revision == 1);
    QsLayout committed = q.layout;
    qs_begin_edit(&q); down(&q, 100, 180, 1000);
    event(&q, QS_MOVE, 600, 180, 1040); event(&q, QS_CANCEL, 600, 180, 1050);
    assert(memcmp(&q.layout, &committed, sizeof committed) == 0 && q.mode == QS_EDIT);
    qs_catalog(&q); assert(qs_add(&q, 9));
    qs_finish_edit(&q, 0); assert(memcmp(&q.layout, &committed, sizeof committed) == 0);
    qs_catalog(&q); assert(qs_add(&q, 20)); /* Stable DC identity extends the catalog without renumbering. */
    assert(!qs_add(&q, 20)); qs_finish_edit(&q, 0);
    assert(memcmp(&q.layout, &committed, sizeof committed) == 0);
    /* Sparse/missed move: releasing far away cannot turn into a long press. */
    down(&q, 100, 180, 2000); up(&q, 600, 180, 2600);
    assert(q.mode == QS_OPEN && qs_take_intent(&q) == -1);
    /* Cancel an edge pull and ignore another pointer's up. */
    qs_toggle(&q); down(&q, 500, 8, 3000); event(&q, QS_MOVE, 500, 250, 3050);
    assert(qs_event(&q, (QsEvent){QS_DOWN, 300, 200, 3060, 2}));
    assert(!q.active && q.mode == QS_CLOSED && qs_take_intent(&q) == -1);
    /* Time wrap: elapsed time is unsigned, long press still occurs. */
    qs_toggle(&q); down(&q, 100, 180, UINT32_MAX - 100);
    qs_tick(&q, 400); assert(q.mode == QS_EDIT); up(&q, 100, 180, 410);
    qs_finish_edit(&q, 0);
    QsLayout invalid = committed; invalid.ids[1] = invalid.ids[0];
    assert(!qs_restore(&q, &invalid)); invalid.count = 255; assert(!qs_restore(&q, &invalid));
    /* Page swipes start on a tile too; they never activate or reorder it. */
    QsTouch paging; qs_init(&paging);
    QsLayout nine = paging.layout; nine.count = 9; nine.ids[8] = 10;
    assert(qs_restore(&paging, &nine)); qs_toggle(&paging);
    down(&paging, 700, 180, 0);
    event(&paging, QS_MOVE, 400, 185, 60); up(&paging, 400, 185, 100);
    assert(paging.page == 1 && paging.selected == 10 && qs_take_intent(&paging) == -1);
    assert(memcmp(&paging.layout, &nine, sizeof nine) == 0);
    down(&paging, 500, 400, 200); up(&paging, 900, 400, 300);
    assert(paging.page == 0 && qs_take_intent(&paging) == -1); /* sparse stream, empty cell */
    down(&paging, 100, 180, 400); up(&paging, 500, 180, 500);
    assert(paging.page == 0); /* first-page boundary */
    down(&paging, 500, 180, 600); up(&paging, 460, 180, 650);
    assert(paging.page == 0 && qs_take_intent(&paging) == -1); /* short swipe */
    down(&paging, 700, 180, 700); event(&paging, QS_MOVE, 300, 180, 740);
    event(&paging, QS_CANCEL, 300, 180, 750);
    assert(paging.page == 0 && qs_take_intent(&paging) == -1);
    down(&paging, 700, 180, 800); up(&paging, 500, 500, 900);
    assert(paging.page == 0 && qs_take_intent(&paging) == -1); /* diagonal */
    down(&paging, 700, 180, 1000); qs_tick(&paging, 1480);
    event(&paging, QS_MOVE, 100, 180, 1500); up(&paging, 100, 180, 1520);
    assert(paging.mode == QS_EDIT && paging.page == 0 && paging.layout.ids[0] == 2);
    assert(qs_take_intent(&paging) == -1); /* reorder has priority once editing */
    qs_finish_edit(&paging, 0);
    down(&paging, 300, 180, 1600); up(&paging, 300, 180, 1650);
    assert(paging.mode == QS_OPEN && paging.selected == 1 && qs_take_intent(&paging) == 1);
    down(&paging, 100, 180, 1700); qs_tick(&paging, 2180);
    assert(qs_page(&paging, 1) && paging.page == 1);
    event(&paging, QS_CANCEL, 100, 180, 2200);
    assert(paging.page == 0 && paging.selected == 1 && paging.mode == QS_OPEN);
    /* Exercise many reorder/cancel/add/page sequences; identities never duplicate. */
    uint32_t seed = 7;
    for (unsigned n = 0; n < 5000; ++n) {
        seed = seed * 1664525u + 1013904223u;
        qs_begin_edit(&q);
        int a = (int)((seed >> 8) % 8), b = (int)((seed >> 16) % 8);
        q.page = 0;
        down(&q, 80 + (a % 4) * 244, 160 + (a / 4) * 200, n * 1000);
        event(&q, QS_MOVE, 80 + (b % 4) * 244, 160 + (b / 4) * 200, n * 1000 + 50);
        event(&q, (seed & 1) ? QS_UP : QS_CANCEL, 80, 160, n * 1000 + 60);
        qs_catalog(&q); qs_add(&q, (uint8_t)(seed % QS_CATALOG_SIZE));
        qs_finish_edit(&q, (int)((seed >> 2) & 1));
        assert(qs_layout_valid(&q.layout) && !q.active && !q.editing);
    }
    puts("PASS: edge gestures, in-place selection, horizontal swipes/bounds/cancel/axis, long-press reorder priority, add, restore, time wrap, 5000 invariant sequences");
    return 0;
}
