#include "qs_tiles_touch.h"

enum { NONE, EDGE, GRID, STRIP, MINUS, PLUS, MORE, DRAG, PASS };
static int absolute(int n) { return n < 0 ? -n : n; }
static int inside(int x, int y) { return x >= 0 && x < 1024 && y >= 0 && y < 682; }
static int cell(int x, int y) {
    if (x < 0 || x >= 1024) return -1;
    if (y >= 77 && y < 300) return x / 256;
    if (y >= 308 && y < 531) return 4 + x / 256;
    return -1;
}
static void end(QttState *t) { t->active = 0; t->gesture = NONE; }
static QttResult result(const QttState *t, int consumed) {
    QttResult out = {0}; out.consumed = (uint8_t)consumed; out.page = t->page; return out;
}
void qtt_init(QttState *t) {
    if (!t) return;
    QttState empty = {0}; *t = empty; t->pages = 1;
}
int qtt_pages(QttState *t, unsigned count) {
    if (!t || t->publishing || t->active || t->page_pending || !count || count > 3) return 0;
    t->pages = (uint8_t)count;
    if (t->page >= count) t->page = (uint8_t)(count - 1);
    t->last_tap = 0;
    return 1;
}
int qtt_page_ready(QttState *t, const QtState *q) {
    if (!t || !q || t->publishing || t->active || !t->page_pending || q->revision == t->revision) return 0;
    t->page_pending = 0; t->revision = q->revision; return 1;
}
int qtt_more_view(QttState *t, int visible) {
    if (!t || t->publishing || !t->open || t->active) return 0;
    t->more_view = visible != 0; t->last_tap = 0; return 1;
}
QttResult qtt_toggle(QttState *t) {
    if (!t || t->publishing) { QttResult empty = {0}; return empty; }
    end(t); t->blocked = 0; t->last_tap = 0; t->more_view = 0;
    t->open = !t->open;
    QttResult out = result(t, 1); out.flags = t->open ? QTT_OPEN : QTT_CLOSE; return out;
}
void qtt_tick(QttState *t, const QtState *q, uint32_t ms) {
    if (t && q && !t->publishing && t->active && t->gesture == GRID && t->origin_slot < QT_SLOTS && !t->moved && !t->more_view &&
        q->revision == t->revision && (uint32_t)(ms - t->down_ms) >= 480u) {
        t->gesture = DRAG; t->last_tap = 0;
    }
}
static void more(QtState *q, unsigned tile, QttResult *out) {
    if (tile >= QT_COUNT) return;
    if (qt_more(q, tile, (uint16_t)(q->tiles[tile].more + 1u), q->revision, &out->intent))
        out->flags |= QTT_MORE;
}
QttResult qtt_event(QttState *t, QtState *q, QttEvent e) {
    QttResult empty = {0};
    if (!t || !q || t->publishing || !q->enabled || q->publishing || (unsigned)e.phase > QTT_CANCEL) return empty;
    if (t->page_pending) return result(t, t->open);
    if (t->blocked) {
        QttResult out = result(t, t->owned);
        if (e.phase == QTT_CANCEL || (e.phase == QTT_UP && e.contacts == 0)) t->blocked = 0;
        return out;
    }
    if (e.contacts > 1 || (t->active && e.pointer != t->pointer)) {
        int consumed = t->active ? t->owned : t->open;
        end(t); t->blocked = e.contacts != 0; t->owned = (uint8_t)consumed; t->last_tap = 0;
        return result(t, consumed);
    }
    if (e.phase == QTT_DOWN) {
        if (t->active) return result(t, t->owned);
        if (e.contacts != 1 || !inside(e.x, e.y) || (!t->open && e.y > 32)) return empty;
        t->active = 1; t->owned = 1; t->pointer = e.pointer;
        t->x0 = t->x = e.x; t->y0 = t->y = e.y; t->down_ms = e.ms;
        t->revision = q->revision; t->moved = 0; t->target_slot = q->focus;
        t->gesture = t->open ? GRID : EDGE;
        int hit = cell(e.x, e.y);
        t->origin_slot = hit >= 0 ? (uint8_t)hit : 255;
        if (t->open && !t->more_view && e.y >= 608) {
            int tile = qt_for_native(q->slots[q->focus]);
            if (tile < 0) { t->gesture = PASS; t->owned = 0; }
            else {
                t->draft = (uint8_t)q->tiles[tile].index;
                t->gesture = e.x < 128 ? MINUS : e.x >= 896 ? MORE : e.x >= 768 ? PLUS : STRIP;
            }
            t->last_tap = 0;
        }
        return result(t, t->owned);
    }
    if (!t->active) return result(t, t->open && e.phase != QTT_UP);
    QttResult out = result(t, t->owned);
    if (t->gesture == PASS) { if (e.phase == QTT_UP || e.phase == QTT_CANCEL) end(t); return out; }
    if (e.phase == QTT_CANCEL || (e.contacts == 0 && e.phase == QTT_MOVE) || q->revision != t->revision) {
        end(t); t->last_tap = 0; return out;
    }
    t->x = e.x; t->y = e.y;
    int dx = (int)e.x - t->x0, dy = (int)e.y - t->y0;
    if (absolute(dx) > 12 || absolute(dy) > 12) t->moved = 1;
    qtt_tick(t, q, e.ms);
    if (t->gesture == DRAG) {
        int hit = cell(e.x, e.y);
        if (hit >= 0) t->target_slot = (uint8_t)hit;
    } else if (t->gesture == STRIP && absolute(dx) > 18 && absolute(dx) * 2 > absolute(dy) * 3) {
        int tile = qt_for_native(q->slots[q->focus]);
        int index = (int)q->tiles[tile].index - dx / 64;
        if (index < 0) index = 0;
        if (index >= q->tiles[tile].count) index = q->tiles[tile].count - 1;
        t->draft = (uint8_t)index;
    }
    if (e.phase != QTT_UP) return out;
    t->active = 0;
    if (t->gesture == EDGE) {
        if (dy >= 96 && dy > absolute(dx)) { t->open = 1; out.flags = QTT_OPEN; }
        t->last_tap = 0;
    } else if (t->gesture != DRAG && dy <= -64 && absolute(dy) * 2 > absolute(dx) * 3) {
        if (t->more_view) { t->more_view = 0; out.flags = QTT_BACK; }
        else { t->open = 0; out.flags = QTT_CLOSE; }
        t->last_tap = 0;
    } else if (t->gesture == DRAG && t->origin_slot < QT_SLOTS) {
        if (inside(e.x, e.y) && cell(e.x, e.y) == t->target_slot) {
            uint8_t slots[QT_SLOTS];
            for (unsigned i = 0; i < QT_SLOTS; ++i) slots[i] = q->slots[i];
            unsigned from = t->origin_slot, to = t->target_slot; uint8_t id = slots[from];
            if (from < to) for (unsigned i = from; i < to; ++i) slots[i] = slots[i + 1];
            else for (unsigned i = from; i > to; --i) slots[i] = slots[i - 1];
            slots[to] = id;
            if (from != to && qt_layout(q, slots)) { out.flags = QTT_REORDER; out.slot = (uint8_t)to; }
            qt_focus(q, to);
        }
        t->last_tap = 0;
    } else if (t->gesture == GRID && !t->more_view && absolute(dx) >= 80 && absolute(dx) > absolute(dy)) {
        int page = t->page + (dx < 0 ? 1 : -1);
        if (page >= 0 && page < t->pages) {
            t->page = (uint8_t)page; t->page_pending = 1;
            out.flags = QTT_PAGE; out.page = t->page;
        }
        t->last_tap = 0;
    } else if (t->gesture == GRID && !t->moved && t->origin_slot < QT_SLOTS &&
               cell(e.x, e.y) == t->origin_slot && !t->more_view) {
        unsigned slot = t->origin_slot;
        qt_focus(q, slot); out.flags = QTT_SELECT; out.slot = (uint8_t)slot;
        int tile = qt_for_native(q->slots[slot]);
        if (tile >= 0 && t->last_tap == slot + 1 && (uint32_t)(e.ms - t->tap_ms) <= 350u &&
            absolute(e.x - t->tap_x) <= 24 && absolute(e.y - t->tap_y) <= 24) {
            more(q, (unsigned)tile, &out); t->last_tap = 0;
        } else {
            t->last_tap = (uint8_t)(slot + 1); t->tap_ms = e.ms; t->tap_x = e.x; t->tap_y = e.y;
        }
    } else if (t->gesture == STRIP && inside(e.x, e.y) && e.y >= 608 && absolute(dx) * 2 > absolute(dy) * 3) {
        int tile = qt_for_native(q->slots[q->focus]);
        if (qt_request(q, (unsigned)tile, t->draft, t->revision, &out.intent)) out.flags = QTT_SET;
        t->last_tap = 0;
    } else if (!t->moved && e.y >= 608 && inside(e.x, e.y)) {
        int tile = qt_for_native(q->slots[q->focus]);
        if (t->gesture == MORE && e.x >= 896) more(q, (unsigned)tile, &out);
        else if ((t->gesture == MINUS && e.x < 128) || (t->gesture == PLUS && e.x >= 768 && e.x < 896)) {
            if (qt_step(q, (unsigned)tile, t->gesture == PLUS ? 1 : -1, t->revision, &out.intent)) out.flags = QTT_SET;
        }
        t->last_tap = 0;
    } else t->last_tap = 0;
    end(t);
    return out;
}

int qtt_publish(QttState *t, const QtState *q, const QtSink *sink) {
    if (!t || !q || t->publishing || q->publishing || !sink || !sink->integer || !sink->text) return 0;
    t->publishing = 1;
    int slot = t->active && t->gesture == DRAG ? t->target_slot : q->focus;
    int custom = qt_for_native(q->slots[q->focus]) >= 0;
    int shown = t->open && !t->page_pending;
    sink->integer(sink->context, "FPQS_PanelOn", shown);
    sink->integer(sink->context, "FPQS_TouchLegacyCursor", !t->open);
    sink->integer(sink->context, "FPQS_TouchFocusOn", shown && !t->more_view);
    sink->integer(sink->context, "FPQS_TouchFocusX", (unsigned)(slot % 4) * 256u);
    sink->integer(sink->context, "FPQS_TouchFocusY", slot < 4 ? 77 : 308);
    sink->integer(sink->context, "FPQS_TouchFooterOn", shown && !t->more_view && custom);
    sink->integer(sink->context, "FPQS_TouchLegacyFooter", !custom);
    int tile = qt_for_native(q->slots[q->focus]);
    sink->text(sink->context, "FPQS_TouchFooterText", tile < 0 ? " " : q->tiles[tile].text);
    char page[] = "1/1"; page[0] = (char)('1' + t->page); page[2] = (char)('0' + t->pages);
    sink->text(sink->context, "FPQS_TouchPageText", page);
    t->publishing = 0;
    return 1;
}
