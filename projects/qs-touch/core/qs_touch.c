#include "qs_touch.h"

enum { G_NONE, G_EDGE, G_ITEM, G_HANDLE, G_BLOCKED, G_PAGE };
static int absolute(int n) { return n < 0 ? -n : n; }
static int64_t distance(QsTouch *q, int x, int y) {
    int64_t dx = x - q->x0, dy = y - q->y0;
    return dx * dx + dy * dy;
}
static int hit(QsTouch *q, int x, int y) {
    /* Native QS proportions: edge-to-edge 4x2 cells, separate adjustment strip. */
    if (x < 0 || x >= QS_WIDTH || y < 110 || y >= 534) return -1;
    int col = x / 256, row = (y - 110) / 212;
    int at = q->page * QS_PAGE_SIZE + row * 4 + col;
    return at < q->layout.count ? at : -1;
}
static void contact_end(QsTouch *q) {
    q->active = 0; q->gesture = G_NONE; q->held = -1; q->drag = -1;
}
static void reorder(QsTouch *q, int from, int to) {
    uint8_t id = q->layout.ids[from];
    if (from < to) for (int n = from; n < to; ++n) q->layout.ids[n] = q->layout.ids[n + 1];
    else for (int n = from; n > to; --n) q->layout.ids[n] = q->layout.ids[n - 1];
    q->layout.ids[to] = id;
}
int qs_layout_valid(const QsLayout *layout) {
    if (!layout || !layout->count || layout->count > QS_MAX_ITEMS) return 0;
    uint32_t seen = 0;
    for (unsigned n = 0; n < layout->count; ++n) {
        unsigned id = layout->ids[n];
        if (id >= QS_CATALOG_SIZE || (seen & (1u << id))) return 0;
        seen |= 1u << id;
    }
    return 1;
}
void qs_init(QsTouch *q) {
    QsTouch zero = {0}; *q = zero;
    q->layout.count = 8;
    for (unsigned n = 0; n < 8; ++n) q->layout.ids[n] = (uint8_t)n;
    q->saved = q->layout; q->held = q->drag = q->intent = -1;
    q->selected = 0;
}
int qs_restore(QsTouch *q, const QsLayout *layout) {
    if (q->active || q->editing || !qs_layout_valid(layout)) return 0;
    q->layout = *layout; q->saved = *layout; q->page = 0;
    q->selected = (int8_t)q->layout.ids[0]; return 1;
}
void qs_begin_edit(QsTouch *q) {
    if (q->mode != QS_OPEN) return;
    q->saved = q->layout; q->editing = 1; q->mode = QS_EDIT;
}
int qs_finish_edit(QsTouch *q, int commit) {
    if (!q->editing) return 0;
    int changed = q->layout.count != q->saved.count;
    for (unsigned n = 0; n < q->layout.count && !changed; ++n)
        changed = q->layout.ids[n] != q->saved.ids[n];
    if (!commit) q->layout = q->saved;
    else if (changed) q->layout.revision = q->saved.revision + 1u;
    q->saved = q->layout; q->editing = 0; q->mode = QS_OPEN;
    q->page = 0; q->selected = (int8_t)q->layout.ids[0]; contact_end(q);
    return commit && changed;
}
void qs_catalog(QsTouch *q) {
    if (q->mode == QS_OPEN) qs_begin_edit(q);
    if (q->mode == QS_EDIT && !q->active) q->mode = QS_CATALOG;
}
int qs_add(QsTouch *q, uint8_t id) {
    if (q->mode != QS_CATALOG || id >= QS_CATALOG_SIZE || q->layout.count >= QS_MAX_ITEMS) return 0;
    for (unsigned n = 0; n < q->layout.count; ++n) if (q->layout.ids[n] == id) return 0;
    q->layout.ids[q->layout.count++] = id;
    q->page = (uint8_t)((q->layout.count - 1) / QS_PAGE_SIZE);
    q->mode = QS_EDIT; return 1;
}
int qs_page(QsTouch *q, int delta) {
    if (q->mode != QS_OPEN && q->mode != QS_EDIT) return 0;
    int page = q->page + delta, max = (q->layout.count - 1) / QS_PAGE_SIZE;
    if (page < 0 || page > max || (q->active && q->drag < 0 && q->gesture != G_PAGE)) return 0;
    q->page = (uint8_t)page;
    q->selected = (int8_t)q->layout.ids[page * QS_PAGE_SIZE]; return 1;
}
void qs_toggle(QsTouch *q) {
    if (q->active) qs_event(q, (QsEvent){QS_CANCEL, q->x, q->y, q->down_ms, q->pointer});
    if (q->editing) { qs_finish_edit(q, 1); return; }
    q->mode = q->mode == QS_CLOSED ? QS_OPEN : QS_CLOSED;
    q->reveal = q->mode == QS_OPEN ? QS_HEIGHT : 0;
}
void qs_tick(QsTouch *q, uint32_t ms) {
    if (q->active && q->gesture == G_ITEM && !q->moved && q->mode == QS_OPEN &&
        (uint32_t)(ms - q->down_ms) >= QS_LONG_PRESS_MS) {
        qs_begin_edit(q); q->drag = q->held;
    }
}
int qs_event(QsTouch *q, QsEvent e) {
    if (e.type == QS_DOWN) {
        if (q->active) {
            /* A second finger cancels the QS gesture; adapter drains both contacts. */
            if (e.pointer != q->pointer)
                qs_event(q, (QsEvent){QS_CANCEL, q->x, q->y, e.ms, q->pointer});
            return 1;
        }
        if (q->mode == QS_CLOSED && (e.y < 0 || e.y > 32 || e.x < 0 || e.x >= QS_WIDTH)) return 0;
        q->active = 1; q->pointer = e.pointer; q->down_ms = e.ms;
        q->x0 = q->x = e.x; q->y0 = q->y = e.y; q->moved = 0;
        q->drag_start = q->layout; q->edit_origin = q->editing;
        q->page_start = q->page; q->selected_start = q->selected;
        q->held = q->drag = -1; q->gesture = G_BLOCKED;
        if (q->mode == QS_CLOSED) q->gesture = G_EDGE;
        else if (q->mode == QS_OPEN || q->mode == QS_EDIT) {
            q->held = (int8_t)hit(q, e.x, e.y);
            if (q->held >= 0) q->gesture = G_ITEM;
            else if (e.y < 100 || e.y >= 658) q->gesture = G_HANDLE;
        }
        return 1;
    }
    if (!q->active || e.pointer != q->pointer) return q->mode != QS_CLOSED;
    if (e.type == QS_CANCEL) {
        if (q->gesture == G_EDGE) { q->mode = QS_CLOSED; q->reveal = 0; }
        else {
            if (q->drag >= 0) q->layout = q->drag_start;
            q->page = q->page_start; q->selected = q->selected_start;
            if (!q->edit_origin && q->editing) { q->editing = 0; q->mode = QS_OPEN; }
            q->reveal = QS_HEIGHT;
        }
        contact_end(q); return 1;
    }
    /* Mark movement before recognizing a long press, including sparse streams. */
    q->x = e.x; q->y = e.y;
    if (distance(q, e.x, e.y) > 12 * 12) q->moved = 1;
    qs_tick(q, e.ms);
    int dy = e.y - q->y0, dx = e.x - q->x0;
    if (q->mode == QS_OPEN && q->y0 >= 110 && q->y0 < 534 &&
        (q->gesture == G_ITEM || q->gesture == G_BLOCKED) &&
        absolute(dx) > 18 && absolute(dx) * 2 > absolute(dy) * 3)
        q->gesture = G_PAGE;
    if (q->gesture == G_EDGE) {
        if (q->mode == QS_CLOSED && absolute(dx) > 12 && absolute(dx) > absolute(dy)) q->gesture = G_BLOCKED;
        else if (dy > 12 && dy > absolute(dx)) q->mode = QS_PULLING;
        if (q->mode == QS_PULLING) q->reveal = (uint16_t)(dy < 0 ? 0 : dy > QS_HEIGHT ? QS_HEIGHT : dy);
    } else if (q->gesture == G_HANDLE && dy < -12) {
        q->reveal = (uint16_t)(QS_HEIGHT + dy < 0 ? 0 : QS_HEIGHT + dy);
    } else if (q->gesture == G_ITEM && q->mode == QS_EDIT && q->moved) {
        if (q->drag < 0) q->drag = q->held;
        int at = hit(q, e.x, e.y);
        if (at >= 0 && at != q->drag) { reorder(q, q->drag, at); q->drag = (int8_t)at; }
    }
    if (e.type != QS_UP) return 1;
    if (q->gesture == G_EDGE) {
        q->mode = q->reveal >= 180 ? QS_OPEN : QS_CLOSED;
        q->reveal = q->mode == QS_OPEN ? QS_HEIGHT : 0;
    } else if (q->gesture == G_HANDLE) {
        if (dy <= -120 && !q->editing) { q->mode = QS_CLOSED; q->reveal = 0; }
        else q->reveal = QS_HEIGHT;
    } else if (q->gesture == G_PAGE) {
        if (absolute(dx) >= 80 && absolute(dx) > absolute(dy)) qs_page(q, dx < 0 ? 1 : -1);
    } else if (q->gesture == G_ITEM && q->mode == QS_OPEN && !q->moved && hit(q, e.x, e.y) == q->held) {
        q->selected = q->intent = (int8_t)q->layout.ids[(unsigned)q->held];
    }
    contact_end(q); return 1;
}
int qs_take_intent(QsTouch *q) { int id = q->intent; q->intent = -1; return id; }
