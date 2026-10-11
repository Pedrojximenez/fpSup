#ifndef SL_MENU_H
#define SL_MENU_H
#include <stdint.h>

/* Sensor Lab: the CINE recording settings page (B2_5) with MODE and SIZE rows
 * under the frame rate, shown only while the resolution is CUSTOM (the page's
 * own SL_CustomChange group; projects/open-gate/build/sl_b25_page.py).
 *
 * The late launcher arms the ten SLX hooks only after the private page is
 * installed and their stock words are proven in the shared journal. B2_5 is
 * parsed every time it is shown, from its 44-byte runtime entry in the shared
 * NBU reader (+08 = page offset from the NBU base). So:
 *
 *   - the page rides in fpSup.BIN after the loader's 61440 bytes ("SLMP"
 *     block) and is read into memory that is never freed;
 *   - its private strings get offsets from the shared pool (fpSup/uishare);
 *   - the rows' six integers are registered once, 0, in the UI variable
 *     registry: memory only, nothing is written to the settings store;
 *   - then B2_5's page offset is switched.
 *
 * All or nothing: every runtime structure is checked against what the stock
 * firmware builds before anything is written; any mismatch installs nothing. */

#define SL_MENU_MAGIC       0x504D4C53u   /* "SLMP", the card file block */
#define SL_MENU_FILE_HEADER 0x24u
#define SL_MENU_VERSION     4u      /* 2: + private NBR; 3: + pages pack; 4: refs into the pages pack */
#define SL_MENU_PAGES_REF   0x80000000u   /* a reference's offset is in the pages pack */
/* right past the loader's MAXLEN (fp_usb_shell/asm/loader.S) */
#define SL_MENU_AT          0xF000u
#if defined(SL_CALC_ONLY)
#define SL_MENU_VARIABLES   193u
#else
#define SL_MENU_VARIABLES   49u
#endif
#if defined(SL_CALC_ONLY)
#define SL_MENU_STRINGS     256u    /* sidebar diagram bindings and private strings */
#define SL_MENU_TEXT        4096u
#else
#define SL_MENU_STRINGS     128u
#define SL_MENU_TEXT        2048u
#endif
/* names[] that are string variables (type 2): the panel's RWZM fields, "0.32" */
#define SL_MENU_IS_TEXT(n)  ((n) == 5u || (n) == 8u || (n) == 23u || (n) == 25u || ((n) >= 35u && (n) <= 38u) || (n) == 40u || (n) == 41u || (n) == 46u || (n) == 48u || (n) == 49u || ((n)>=57u && (n)<=60u))
#define SL_MENU_LAB_FOCUS   11u     /* names[] index of SL_LabFocus (starts at SL_LAB_FOCUS0) */
#define SL_MODES_MAX        72u     /* the registry has 70 sensor modes */

enum sl_menu_result {
    SL_MENU_INSTALLED = 1,
    SL_MENU_NO_GUI = 2, SL_MENU_NO_SCREEN = 3, SL_MENU_READER = 4,
    SL_MENU_NO_ENTRY = 5, SL_MENU_ROOM = 6, SL_MENU_FILE = 7,
    SL_MENU_FORMAT = 8, SL_MENU_REGISTER = 9, SL_MENU_VARIABLE = 10,
    SL_MENU_POOL = 11,             /* the shared string pool refused */
    SL_MENU_HOOK = 12              /* late hook journal / cave preflight refused */
};

/* names[]: the lab page's OUTPUT info panel integers (sl_modes.c sl_menu_panel,
 * sl_lab_page.py PANEL_VARS): 0 SL_O_W, 1 SL_O_H, 2 SL_O_In (its line switch),
 * 3 SL_O_BH, 4 SL_O_BV, 5 SL_O_SW, 8 SL_O_SH; 6 SL_ModeCount (rows of the MODE
 * list); 7 MV_SLScale, 9 MV_SLBin (OUTPUT's Squeeze / Binning rows), 10 MV_SLRwzm
 * (unused); 11 SL_LabFocus (the lab page's focused object, its own MENU_Level3;
 * starts at the tab bar, SL_LAB_FOCUS0 from the builder), 12..15 SL_F_Bit / Fps /
 * Width / Prop (FILTER), 16 SL_M_Sel (MODE placeholder), 17 SL_LabTab (the open
 * tab); 18 SL_O_Key (the panel editor's key code, sl_lab_page.EDITOR_KEYS),
 * 19..22 SL_O_A0..A3 (the editing arrows of W / H / binH / binV).  The registry BORROWS each name,
 * so they live here, in state that is never freed. */
struct sl_menu {
    uint32_t result;                /* enum sl_menu_result, 0 = never tried */
    uintptr_t app, reader, entry;   /* the native objects switched */
    uintptr_t page, pool;
    uint32_t page_len, pool_len, file_len;
    uint32_t registered;            /* how many this boot registered */
    uint32_t reads, on_reads;       /* unused here; kept for the copied layout */
    uint32_t names[SL_MENU_VARIABLES][5];
    /* the CUSTOM-only lists (sl_lists.py), not registered here: sl_excl.S does
     * it on the UI thread through C05E84D8, once. 0 = the file has none. */
    uintptr_t nbr;
    uint32_t nbr_len;
    /* descriptors of the stock EXCL_FrameRate / EXCL_CinemaDNGQuality (+08 = value) */
    uintptr_t excl_rate, excl_bit;
    /* the private pages (sl_pages.py): registered on the UI thread (sl_modes.c
     * sl_menu_ui) through the same stock loader, which builds their screens */
    uintptr_t pages;
    uint32_t pages_len;
    uint32_t pages_state;           /* 0 not tried, 1 registered, 3 refused, 4 no room for screens */
    uintptr_t pages_reader;
    /* the MODE list (sl_modes.c): rewritten in place on the UI thread */
    uintptr_t count_desc;           /* SL_ModeCount's descriptor */
    uint32_t modes_key;             /* bit | rate << 8 | 1 << 31 of the last attempt, 0 = never */
    uint32_t modes_step;            /* enum sl_modes_step of the last attempt */
    uint32_t modes_rows, modes_runs;
    uint32_t filter_key;            /* FILTER's five rows (4 bits each) the list was built for */
    uint32_t excl_key;              /* the mode the record settings' rate / bit rows were greyed for, + 1 */
    uint32_t rec_cap_w, rec_cap_h;  /* the largest record matrix; 0 = REC_MAX_W / _H (a test lifts it) */
    uint32_t axis_armed;
    uint32_t sb_vis_w, sb_vis_h;    /* standby live view's visible size (declare_post), 0 = the old rule */            /* AXIS is written only after the user acts on the Sensor Lab page */
    uint8_t mode_ids[SL_MODES_MAX]; /* row -> sensor mode id */
    uintptr_t modes_inst, modes_iface;  /* what the last attempt got (for mem get) */
    /* OUTPUT's info panel, edited in place (sl_modes.c panel_key) */
    uint32_t out_w, out_h, bin_h, bin_v;
    uint32_t edit_field, editing;    /* 0..3 = W, H, binH, binV */
    uint32_t ratio;                  /* the Ratio row last applied (sl_lists SCALE_ROWS) */
    uint32_t mode_sel;               /* the MODE row last applied (SL_M_Sel) */
    uint32_t ro_w, ro_h, ro_changed; /* OUTPUT's readout: the chosen mode's raster (0: the sensor) */
    uint32_t ro_sx, ro_sy;           /* its reduction (+0x4C / +0x50): AUTO's shape = readout x it */
    uint32_t crop_w, crop_h;         /* Crop row: pixels cut from the readout, centred (0 = none) */
    uint32_t crop_field, crop_editing;
    char rwzm_text[2][8];
    char rate_text[24];              /* SL_O_Rate: the data rate, "29.97p 1101 MB/s" */
    char mode_text[24];              /* SL_M_Text: the MODE row's summary, "M98 3032x2012" */
    char diag_text[4][32];
    char tab_text[16];               /* SL_M_Tab: the MODES tab's caption, "MODES (62)" */
    char crop_text[32];              /* SL_C_Text: the Crop row, "-1024x-540 (5040x2872)" */
    char diag_crop[32];              /* SL_D_CTxt: the diagram's crop label */           /* SL_D_GTxt / RTxt / Fps / Rs: the MODE tab's diagram */            /* SL_O_SW / SL_O_SH: the GUI queue keeps the pointer */
    uint32_t key_tick, key_last, key_run;   /* hold-to-accelerate */
    uintptr_t core_base;             /* relocated Sensor Lab USER block; set by the late UI launcher */
    uint32_t bin_kh, bin_kv;         /* x3 kernel per axis, imx410_binfilt.KERNELS index 0..5 */
    uint32_t bin_mode;               /* the record's control bits, both axes: 0 = record 0, 1 = record 1 */
#if defined(SL_CALC_ONLY)
    uint32_t canvas[29], canvas_valid;
    uintptr_t export_ctx;
    char export_text[32];
    uint32_t crop_lock, lens_on, lens_factor, small_edit;
    uint32_t applied_geometry[8], applied_valid;
    char output_text[32], bins_text[32], lens_text[32], final_text[32];
#endif
    char bin_caption[32];            /* SL_O_BTxt: "bin" / "H(1,6,1) soft" / "(1,1,1)x(1,14,1) std" */
};

enum sl_modes_step {
    SL_MODES_OK = 0, SL_MODES_NOT_INSTALLED = 1, SL_MODES_NO_IMAGER = 2, SL_MODES_FIND = 3,
    SL_MODES_COUNT = 4, SL_MODES_LOAD = 5, SL_MODES_GET = 6, SL_MODES_IFACE = 7,
    SL_MODES_NOT_CSV = 8, SL_MODES_DELETE = 9, SL_MODES_INSERT = 10, SL_MODES_WRITE = 11,
    SL_MODES_NOTIFY = 12
};

/* On the UI thread, before any page is built (sl_excl.S ROLE 7): register the
 * private pages once, then, under CUSTOM, the MODE list (sl_menu_modes). */
uint32_t sl_menu_ui(struct sl_menu *, uint32_t custom);
/* After the frame-rate / bit-depth setter callbacks (sl_excl.S ROLE 12-14). */
uint32_t sl_menu_live(struct sl_menu *);
/* OUTPUT's info panel: post its integers from MV_SLScale / MV_SLBin (sl_modes.c). */
uint32_t sl_menu_panel(struct sl_menu *);
/* On the UI thread, before a page is built (sl_menu_ui, under CUSTOM):
 * when bit depth or FILTER changes, list the sensor modes that can run at a
 * supported rate and rewrite the SL_MODE model to them
 * ("M<id>", or one "No matching" row), then SL_ModeCount.  Returns the step. */
uint32_t sl_menu_modes(struct sl_menu *);
/* The scan alone: ids of the modes og3krecipe would accept for (bit, rate
 * index), or any supported rate when ridx == SL_NRATE.  Quality order;
 * returns how many (0..SL_MODES_MAX). */
uint32_t sl_menu_scan_modes(uint32_t bit, uint32_t ridx, uint8_t *ids);

/* `area` is memory owned for the rest of the boot (never freed), 8-aligned;
 * it receives the file object, the page and the pool. */
uint32_t sl_menu_install(struct sl_menu *, uintptr_t area, uint32_t area_bytes);

/* names[index]'s current value into *value; 1 if read, 0 if not installed. */
uint32_t sl_menu_value(struct sl_menu *, uint32_t index, uint32_t *value);

#if defined(SL_MENU_HOST_TEST)
struct sl_menu_natives {
    uint32_t (*read)(uintptr_t);
    void (*write)(uintptr_t, uint32_t);
    uint32_t (*read_byte)(uintptr_t);
    void (*write_byte)(uintptr_t, uint32_t);
    void (*f_ctor)(uintptr_t, uint32_t);
    uint32_t (*f_open)(uintptr_t, const char *, uint32_t);
    uint32_t (*f_read)(uintptr_t, uintptr_t, uint32_t, uint32_t *);
    void (*f_close)(uintptr_t);
    void (*f_dtor)(uintptr_t, uint32_t);
    uint32_t (*lookup)(uintptr_t, const char *, uintptr_t *);
    uint32_t (*reg)(uintptr_t, uint32_t, const uint32_t *);
    void (*publish)(void);
    /* sl_modes.c: the resource / model natives */
    uint32_t (*res_find)(uintptr_t, const char *, uintptr_t *);
    uint32_t (*res_count)(uintptr_t, uint32_t *);
    uint32_t (*res_load)(uintptr_t);
    uint32_t (*res_get)(uintptr_t, uintptr_t *);
    uint32_t (*model_iface)(uintptr_t, uintptr_t *);
    uint32_t (*notify)(uintptr_t, uint32_t *);
    uint32_t (*m_rows)(uintptr_t, uint32_t *);
    uint32_t (*m_current)(uintptr_t, uint32_t);
    uint32_t (*m_string)(uintptr_t, uint32_t, const char *);
    uint32_t (*m_insert)(uintptr_t, uint32_t, uint32_t);
    uint32_t (*m_delete)(uintptr_t, uint32_t, uint32_t);
    uint32_t (*nbr_register)(uintptr_t, uintptr_t, uint32_t, uintptr_t *);
    uintptr_t (*settings)(void);
    uint32_t (*get_res)(uintptr_t);
    uint32_t (*get_bit)(uintptr_t);
    uint32_t (*get_rate)(uintptr_t);
    uint32_t (*subscribe)(const void *, uint32_t (*)(uintptr_t, uintptr_t));
    uint32_t (*post_int)(const void *, uint32_t);
    uint32_t (*post_str)(const void *, const char *);
    uint32_t (*tick_ms)(void);
};
extern const struct sl_menu_natives sl_menu_test_natives;
#endif
#endif
