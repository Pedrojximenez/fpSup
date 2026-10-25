#ifndef FP_QS_TILES_TOUCH_H
#define FP_QS_TILES_TOUCH_H
#include "qs_tiles.h"

/* Normalized events only. These are not guessed XC_TouchPanelData flag values. */
typedef enum { QTT_DOWN, QTT_MOVE, QTT_UP, QTT_CANCEL } QttPhase;
typedef struct {
    QttPhase phase;
    int16_t x, y;
    uint32_t ms, pointer;
    uint8_t contacts;
} QttEvent;
enum { QTT_SELECT = 1, QTT_OPEN = 2, QTT_CLOSE = 4, QTT_SET = 8,
       QTT_MORE = 16, QTT_BACK = 32, QTT_REORDER = 64, QTT_PAGE = 128 };
typedef struct {
    uint16_t flags;
    uint8_t consumed, slot, page;
    QtIntent intent;
} QttResult;
typedef struct {
    uint8_t open, more_view, active, owned, blocked, gesture, moved, publishing;
    uint8_t pages, page, page_pending, origin_slot, target_slot, draft, last_tap;
    int16_t x0, y0, x, y, tap_x, tap_y;
    uint32_t pointer, down_ms, revision, tap_ms;
} QttState;

void qtt_init(QttState *);
int qtt_pages(QttState *, unsigned count);
int qtt_page_ready(QttState *, const QtState *); /* after layout owner installs the new slots */
int qtt_more_view(QttState *, int visible); /* set only after the detail view exists */
QttResult qtt_toggle(QttState *);
QttResult qtt_event(QttState *, QtState *, QttEvent);
void qtt_tick(QttState *, const QtState *, uint32_t ms);
int qtt_publish(QttState *, const QtState *, const QtSink *);
#endif
