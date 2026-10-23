#ifndef FP_QS_TILES_H
#define FP_QS_TILES_H
#include <stdint.h>

/* Private tile state and intent routing. No firmware addresses or settings I/O. */
enum { QT_FORMAT, QT_DC, QT_RES, QT_FPS, QT_COUNT, QT_SLOTS = 8,
       QT_TEXT_CAP = 48, QT_OPTIONS_MAX = 64 };
typedef struct {
    uint16_t count, index, more;
    char text[QT_TEXT_CAP], detail[QT_TEXT_CAP];
} QtTile;
typedef struct {
    QtTile tiles[QT_COUNT];
    uint8_t slots[QT_SLOTS], focus, configured, enabled, publishing;
    uint32_t revision;
} QtState;
typedef enum { QT_SET, QT_MORE } QtAction;
typedef struct { QtAction action; uint8_t tile; uint16_t index; uint32_t revision; } QtIntent;
typedef struct {
    void *context;
    void (*integer)(void *, const char *, uint32_t);
    void (*text)(void *, const char *, const char *);
} QtSink;

int qt_init(QtState *, const uint8_t slots[QT_SLOTS]);
int qt_for_native(unsigned native_ui_id);
int qt_for_touch(unsigned preview_stable_id);
/* Canonical service feedback, not a camera setter. Invalid feedback changes nothing. */
int qt_configure(QtState *, unsigned tile, unsigned count, unsigned index,
                 const char *text, const char *detail);
int qt_start(QtState *); /* requires all four canonical values */
int qt_focus(QtState *, unsigned slot);
int qt_layout(QtState *, const uint8_t slots[QT_SLOTS]);
/* Requests do not change canonical values. Re-publish after rejecting an intent
 * to reconcile the native two-way holder. Use revision to reject stale input. */
int qt_request(const QtState *, unsigned tile, unsigned index, uint32_t revision, QtIntent *);
int qt_step(const QtState *, unsigned tile, int delta, uint32_t revision, QtIntent *);
int qt_more(QtState *, unsigned tile, unsigned counter, uint32_t revision, QtIntent *);
int qt_publish(QtState *, const QtSink *);
#endif
