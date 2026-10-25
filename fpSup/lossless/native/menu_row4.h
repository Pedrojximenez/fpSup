#ifndef FPLOSSLESS_MENU_ROW4_H
#define FPLOSSLESS_MENU_ROW4_H
#include <stdint.h>
#include "sloader4.h"

/* Loader v4: the Lossless-CDNG switch is a TOGGLE row on the fpSup page
 * (svc->page_add), not a row composed onto the stock CINE page -- the user
 * 2026-10-22: "搬到 fpSup 頁的開關列".  Same interface as menu_page.h, so
 * card.c's take decision (fpl_menu_on at REC) and its idle save
 * (fpl_menu_now, settings_poll) are unchanged.
 *
 * The value is one word here.  The core keeps a pointer to `row`, its title
 * and choices: they live in this struct, in the card state, never freed.
 * The strings are written at install from immediates -- the C has no data
 * section (elf_text refuses one). */

enum fpl_menu_result {
    FPL_MENU_INSTALLED = 1,
    FPL_MENU_NO_SVC = 2,            /* no service table, or older than page_add */
    FPL_MENU_ROW = 3                /* page_add refused: ui_result is its code */
};

struct fpl_menu {
    uint32_t result;                /* enum fpl_menu_result, 0 = never tried */
    uint32_t value;                 /* 0 OFF, 1 ON */
    uint32_t initial;               /* the saved state the row starts with */
    uint32_t ui_result;             /* page_add's result (row number or < 0) */
    uint32_t registered;            /* 1 once the row is on the page */
    uint32_t reads, on_reads;       /* REC-time lookups; how many said ON */
    uint32_t sets;                  /* values the row accepted */
    struct sl_row row;
    const char *choices[2];
    uint32_t title[4], off[1], on[1];
};

/* Put the row on the fpSup page; call from the sup's entry (page_add works
 * only while it runs).  Starts at m->initial. */
uint32_t fpl_menu_install_row(struct fpl_menu *, const struct sl_svc *);

/* The row's value (0 OFF, 1 ON), or UINT32_MAX when it is not installed. */
uint32_t fpl_menu_now(struct fpl_menu *);

/* 1 if the row reads ON right now; 0 for OFF or not installed. */
uint32_t fpl_menu_on(struct fpl_menu *);
#endif
