#include "qs_tiles.h"

static const unsigned native_ids[QT_COUNT] = {20, 17, 21, 22};
static const unsigned touch_ids[QT_COUNT] = {6, 20, 4, 5};
static const char *keys[QT_COUNT] = {"Format", "DC", "Res", "FPS"};

static int copy(char *dst, const char *src) {
    unsigned n = 0;
    if (!src) return 0;
    while (n < QT_TEXT_CAP && src[n]) ++n;
    if (n == QT_TEXT_CAP) return 0;
    for (unsigned i = 0; i <= n; ++i) dst[i] = src[i];
    return 1;
}

static int slots_valid(const uint8_t *slots) {
    if (!slots) return 0;
    for (unsigned i = 0; i < QT_SLOTS; ++i) if (slots[i] > 48) return 0;
    return 1;
}

int qt_init(QtState *q, const uint8_t slots[QT_SLOTS]) {
    if (!q || !slots_valid(slots)) return 0;
    QtState initial = {0};
    for (unsigned i = 0; i < QT_SLOTS; ++i) initial.slots[i] = slots[i];
    for (unsigned i = 0; i < QT_COUNT; ++i) {
        initial.tiles[i].text[0] = ' ';
        initial.tiles[i].detail[0] = ' ';
    }
    *q = initial;
    return 1;
}

int qt_for_native(unsigned id) {
    for (unsigned i = 0; i < QT_COUNT; ++i) if (id == native_ids[i]) return (int)i;
    return -1;
}

int qt_for_touch(unsigned id) {
    for (unsigned i = 0; i < QT_COUNT; ++i) if (id == touch_ids[i]) return (int)i;
    return -1;
}

int qt_configure(QtState *q, unsigned tile, unsigned count, unsigned index,
                 const char *text, const char *detail) {
    if (!q || q->publishing || tile >= QT_COUNT || !count || count > QT_OPTIONS_MAX || index >= count) return 0;
    QtTile next = q->tiles[tile];
    if (!text || !*text || !copy(next.text, text) || !copy(next.detail, detail)) return 0;
    next.count = (uint16_t)count;
    next.index = (uint16_t)index;
    q->tiles[tile] = next;
    q->configured |= (uint8_t)(1u << tile);
    ++q->revision;
    return 1;
}

int qt_start(QtState *q) {
    if (!q || q->publishing || q->configured != (1u << QT_COUNT) - 1u) return 0;
    if (!q->enabled) { q->enabled = 1; ++q->revision; }
    return 1;
}

int qt_focus(QtState *q, unsigned slot) {
    if (!q || q->publishing || slot >= QT_SLOTS) return 0;
    if (q->focus != slot) { q->focus = (uint8_t)slot; ++q->revision; }
    return 1;
}

int qt_layout(QtState *q, const uint8_t slots[QT_SLOTS]) {
    if (!q || q->publishing || !slots_valid(slots)) return 0;
    for (unsigned i = 0; i < QT_SLOTS; ++i) q->slots[i] = slots[i];
    ++q->revision;
    return 1;
}

int qt_request(const QtState *q, unsigned tile, unsigned index, uint32_t revision, QtIntent *out) {
    if (!q || !out || q->publishing || !q->enabled || tile >= QT_COUNT || revision != q->revision ||
        index >= q->tiles[tile].count || index == q->tiles[tile].index ||
        qt_for_native(q->slots[q->focus]) != (int)tile) return 0;
    *out = (QtIntent){QT_SET, (uint8_t)tile, (uint16_t)index, revision};
    return 1;
}

int qt_step(const QtState *q, unsigned tile, int delta, uint32_t revision, QtIntent *out) {
    if (!q || tile >= QT_COUNT || (delta != 1 && delta != -1)) return 0;
    int index = (int)q->tiles[tile].index + delta;
    if (index < 0) return 0;
    return qt_request(q, tile, (unsigned)index, revision, out);
}

int qt_more(QtState *q, unsigned tile, unsigned counter, uint32_t revision, QtIntent *out) {
    if (!q || !out || q->publishing || !q->enabled || tile >= QT_COUNT || counter > 65535u || revision != q->revision ||
        counter == q->tiles[tile].more || qt_for_native(q->slots[q->focus]) != (int)tile) return 0;
    q->tiles[tile].more = (uint16_t)counter;
    *out = (QtIntent){QT_MORE, (uint8_t)tile, q->tiles[tile].index, revision};
    return 1;
}

static void name(char *out, const char *key, const char *suffix, unsigned slot) {
    unsigned i = 0;
    const char *parts[] = {"FPQS_", key, suffix};
    for (unsigned p = 0; p < 3; ++p)
        for (unsigned j = 0; parts[p][j]; ++j) out[i++] = parts[p][j];
    if (slot) out[i++] = (char)('0' + slot);
    out[i] = 0;
}

int qt_publish(QtState *q, const QtSink *sink) {
    if (!q || q->publishing || !sink || !sink->integer || !sink->text) return 0;
    q->publishing = 1;
    char var[48];
    for (unsigned i = 0; i < QT_COUNT; ++i) {
        const QtTile *t = &q->tiles[i];
        name(var, keys[i], "Max", 0); sink->integer(sink->context, var, t->count ? t->count - 1u : 0);
        name(var, keys[i], "Index", 0); sink->integer(sink->context, var, t->index);
        name(var, keys[i], "More", 0); sink->integer(sink->context, var, t->more);
        name(var, keys[i], "Text", 0); sink->text(sink->context, var, t->text);
        name(var, keys[i], "Detail", 0); sink->text(sink->context, var, t->detail);
    }
    for (unsigned slot = 0; slot < QT_SLOTS; ++slot) {
        int current = q->enabled ? qt_for_native(q->slots[slot]) : -1;
        name(var, "Legacy", "", slot + 1); sink->integer(sink->context, var, current < 0);
        for (unsigned i = 0; i < QT_COUNT; ++i) {
            name(var, keys[i], "On", slot + 1);
            sink->integer(sink->context, var, current == (int)i);
        }
    }
    int active = q->enabled ? qt_for_native(q->slots[q->focus]) : -1;
    sink->integer(sink->context, "FPQS_LegacyFooter", active < 0);
    sink->integer(sink->context, "FPQS_FooterOn", active >= 0);
    sink->integer(sink->context, "FPQS_DCMoreKeyOn", active == QT_DC);
    sink->text(sink->context, "FPQS_FooterText", active < 0 ? " " : q->tiles[active].detail);
    q->publishing = 0;
    return 1;
}
