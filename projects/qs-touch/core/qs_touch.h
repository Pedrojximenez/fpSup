#ifndef FP_QS_TOUCH_H
#define FP_QS_TOUCH_H
#include <stdint.h>

/* Offline interaction core. No camera addresses, settings setters or I/O. */
enum { QS_WIDTH = 1024, QS_HEIGHT = 682, QS_MAX_ITEMS = 24,
       QS_PAGE_SIZE = 8, QS_CATALOG_SIZE = 21, QS_LONG_PRESS_MS = 480 };
typedef enum { QS_CLOSED, QS_PULLING, QS_OPEN, QS_EDIT, QS_CATALOG } QsMode;
typedef enum { QS_DOWN, QS_MOVE, QS_UP, QS_CANCEL } QsEventType;
typedef struct { QsEventType type; int16_t x, y; uint32_t ms, pointer; } QsEvent;
typedef struct { uint8_t count, ids[QS_MAX_ITEMS]; uint32_t revision; } QsLayout;
typedef struct {
    QsMode mode;
    QsLayout layout, saved, drag_start;
    uint16_t reveal; /* 0..682; renderer owns presentation and settling. */
    uint8_t page, active, gesture, moved, editing, edit_origin, page_start;
    int8_t held, drag, intent, selected, selected_start;
    int16_t x0, y0, x, y;
    uint32_t down_ms, pointer;
} QsTouch;

void qs_init(QsTouch *q);
int qs_layout_valid(const QsLayout *layout);
int qs_restore(QsTouch *q, const QsLayout *layout);
/* Return 1 when this contact belongs to QS, including cancelled edge pulls. */
int qs_event(QsTouch *q, QsEvent event);
void qs_tick(QsTouch *q, uint32_t now_ms);
void qs_toggle(QsTouch *q); /* physical QS key / accessible preview equivalent */
void qs_begin_edit(QsTouch *q);
void qs_catalog(QsTouch *q);
int qs_add(QsTouch *q, uint8_t stable_item_id);
int qs_page(QsTouch *q, int delta);
/* Cancel restores the complete pre-edit layout. Commit emits no file I/O. */
int qs_finish_edit(QsTouch *q, int commit);
/* Activate a QS control in place; this is not a request to open a detail page. */
int qs_take_intent(QsTouch *q); /* item id, or -1; native app owns actual changes */
#endif
