#include "menu_row4.h"

/* menu_row4.h.  Callbacks run on the UI thread: they only read or write one
 * word; saving is card.c's idle poll, as with the stock-page row. */

static int row_get(void *arg)
{
    return (int)((struct fpl_menu *)arg)->value;
}

static int row_set(void *arg, int v)
{
    struct fpl_menu *m = (struct fpl_menu *)arg;
    if (v != 0 && v != 1) return 1;
    m->value = (uint32_t)v;
    if (m->sets != UINT32_MAX) ++m->sets;
    return 0;
}

uint32_t fpl_menu_install_row(struct fpl_menu *m, const struct sl_svc *svc)
{
    int r;
    if (!m) return 0;
    if (!svc || svc->version < 5u || !svc->page_add) return m->result = FPL_MENU_NO_SVC;
    m->title[0] = 0x73736F4Cu;          /* "Loss" */
    m->title[1] = 0x7373656Cu;          /* "less" */
    m->title[2] = 0;                    /* "Lossless" (user 2026-10-25; was "Lossless-CDNG") */
    m->title[3] = 0;
    m->off[0] = 0x0046464Fu;            /* "OFF" */
    m->on[0] = 0x00004E4Fu;             /* "ON"  */
    m->choices[0] = (const char *)m->off;
    m->choices[1] = (const char *)m->on;
    m->value = m->initial <= 1u ? m->initial : 0u;
    m->row.kind = SL_ROW_TOGGLE;
    m->row.n_choices = 2;
    m->row.title = (const char *)m->title;
    m->row.value = 0;
    m->row.get = row_get;
    m->row.set = row_set;
    m->row.choices = m->choices;
    m->row.open = 0;
    m->row.arg = m;
    r = svc->page_add(svc, &m->row);
    m->ui_result = (uint32_t)r;
    if (r < 0) return m->result = FPL_MENU_ROW;
    m->registered = 1;
    return m->result = FPL_MENU_INSTALLED;
}

uint32_t fpl_menu_now(struct fpl_menu *m)
{
    if (!m || m->result != FPL_MENU_INSTALLED) return UINT32_MAX;
    return m->value;
}

uint32_t fpl_menu_on(struct fpl_menu *m)
{
    if (!m || m->result != FPL_MENU_INSTALLED) return 0;
    if (m->reads != UINT32_MAX) ++m->reads;
    if (m->value != 1u) return 0;
    if (m->on_reads != UINT32_MAX) ++m->on_reads;
    return 1;
}
