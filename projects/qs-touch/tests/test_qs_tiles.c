#include "../core/qs_tiles.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned integers, strings;
static void number(void *ctx, const char *key, uint32_t value) {
    QtState *q = ctx;
    QtIntent rejected;
    assert(q->publishing && !qt_step(q, QT_DC, 1, q->revision, &rejected));
    assert(!qt_focus(q, 0));
    ++integers;
    assert(strncmp(key, "FPQS_", 5) == 0);
    printf("I %s %u\n", key, value);
}
static void text(void *ctx, const char *key, const char *value) {
    (void)ctx; ++strings;
    assert(strncmp(key, "FPQS_", 5) == 0);
    printf("T %s %s\n", key, value);
}
int main(void) {
    uint8_t slots[QT_SLOTS] = {20,17,21,22,25,20,21,22};
    QtState q, before;
    QtIntent request;
    assert(qt_init(&q, slots));
    assert(!qt_start(&q));
    assert(!qt_step(&q, QT_FORMAT, 1, q.revision, &request));
    assert(qt_for_native(20) == QT_FORMAT && qt_for_touch(20) == QT_DC);
    assert(qt_for_native(6) == -1 && qt_for_touch(6) == QT_FORMAT);
    assert(qt_for_native(49) == -1 && qt_for_touch(49) == -1);
    const char *values[] = {"CDNG 10bit", "HD", "CUSTOM(16:9)", "29.97p"};
    const char *details[] = {"CinemaDNG", "35.9 x 20.17 mm", "4000 x 2250", "Frame rate"};
    for (unsigned i = 0; i < QT_COUNT; ++i)
        assert(qt_configure(&q, i, 5, 1, values[i], details[i]));
    assert(qt_start(&q));
    before = q;
    assert(!qt_configure(&q, QT_RES, 0, 0, "bad", "bad"));
    assert(!qt_configure(&q, QT_RES, 3, 3, "bad", "bad"));
    char long_text[QT_TEXT_CAP + 1]; memset(long_text, 'x', sizeof long_text); long_text[QT_TEXT_CAP] = 0;
    assert(!qt_configure(&q, QT_RES, 3, 1, long_text, "bad"));
    assert(memcmp(&q, &before, sizeof q) == 0);
    assert(!qt_request(&q, QT_DC, 2, q.revision, &request)); /* not focused */
    assert(qt_step(&q, QT_FORMAT, 1, q.revision, &request));
    assert(request.action == QT_SET && request.index == 2 && request.tile == QT_FORMAT);
    assert(memcmp(&q, &before, sizeof q) == 0); /* intent is not service feedback */
    uint32_t old_revision = q.revision;
    assert(qt_focus(&q, 1));
    assert(!qt_request(&q, QT_FORMAT, 2, old_revision, &request));
    assert(qt_more(&q, QT_DC, 1, q.revision, &request));
    assert(request.action == QT_MORE && request.tile == QT_DC);
    assert(!qt_more(&q, QT_DC, 1, q.revision, &request)); /* duplicate notification */
    assert(qt_more(&q, QT_DC, 65535, q.revision, &request));
    assert(qt_more(&q, QT_DC, 0, q.revision, &request)); /* native counter wrap */
    for (unsigned slot = 0; slot < QT_SLOTS; ++slot) {
        assert(qt_focus(&q, slot));
        int tile = qt_for_native(slots[slot]);
        if (tile < 0) continue;
        assert(qt_step(&q, (unsigned)tile, -1, q.revision, &request));
        assert(request.tile == (unsigned)tile && request.index == 0);
        assert(!qt_step(&q, (unsigned)tile, 2, q.revision, &request));
    }
    assert(qt_focus(&q, 0));
    assert(qt_configure(&q, QT_FORMAT, 5, 0, values[0], details[0]));
    assert(!qt_step(&q, QT_FORMAT, -1, q.revision, &request));
    assert(qt_configure(&q, QT_FORMAT, 5, 4, values[0], details[0]));
    assert(!qt_step(&q, QT_FORMAT, 1, q.revision, &request));
    assert(qt_configure(&q, QT_FORMAT, 5, 1, values[0], details[0]));
    before = q; slots[1] = 49;
    assert(!qt_layout(&q, slots) && memcmp(&before, &q, sizeof q) == 0);
    slots[1] = 17; slots[0] = 25; slots[4] = 20;
    assert(qt_layout(&q, slots) && qt_focus(&q, 4));
    assert(qt_step(&q, QT_FORMAT, 1, q.revision, &request)); /* identity survives reorder */
    slots[0] = 20; slots[4] = 25;
    assert(qt_layout(&q, slots) && qt_focus(&q, 1));
    QtSink sink = {&q, number, text};
    assert(qt_publish(&q, &sink));
    assert(!q.publishing);
    assert(integers == 55 && strings == 9);
    puts("PASS private tile identity, bounds, canonical feedback, stale input, more, reorder and 64-variable contract");
    return 0;
}
