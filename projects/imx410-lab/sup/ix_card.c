/* IMXL fork of rec-core/writer/wr_card.c (sha256 d1cbf67e...): the same task
 * and flag, named "IMXL", plus tick_us for the sink.
 *
 * wr_card -- the camera side of wr: the firmware table, the event flag and the
 * writer task.  Compiled into one unit with bq.c and wr.c by build.py; the
 * entry, claims, hooks and veneers are wr_card.S.  fp 5.02 addresses. */
#include "ix_wr.h"

#define FLG_CREATE   0xC00169ECu    /* tk_cre_flg(&T_CFLG) -> id               */
#define FLG_SET      0xC0016B9Cu    /* tk_set_flg(id, ptn)                     */
#define FLG_WAIT     0xC0016C08u    /* tk_wai_flg(id, ptn, mode, &out, tmo)    */
#define TK_CRE_TSK   0xC0016A58u    /* tk_cre_tsk(&T_CTSK) -> id (main path)   */
#define TK_STA_TSK   0xC0016BC0u    /* tk_sta_tsk(id, 0) -> 0                  */
#define SLEEP_MS     0xC03705D8u    /* -> tk_dly_tsk, as LOSS uses it          */
#define IRQ_OFF      0xC000EC14u
#define IRQ_RESTORE  0xC000EC24u
#define DEV_WRITE    0xC01EB791u    /* C01EB790, Thumb                         */
#define TICK_US      0xC002B6E0u    /* free-running microseconds (loader v4)   */

#define WR_PRI       6u             /* SRecFile's: the device semaphore and the */
                                    /* FS lock have no priority inheritance     */
#define WR_STACK     0x2000u
#define WR_BLOCK     (8u << 20)     /* O2: 8 MiB, an RU and cluster multiple    */

/* T_CFLG {exinf, flgatr, iflgptn, dsname[8]}: TA_TPRI|TA_WMUL|TA_DSNAME as
 * XC_Thread.cpp's.  Word stores: an initialised struct would be .rodata. */
static int flag_create(void) {
    volatile uint32_t p[5];
    p[0] = 0;
    p[1] = 0x49u;
    p[2] = 0;
    p[3] = 0x4C584D49u;             /* "IMXL" */
    p[4] = 0;
    return ((int (*)(volatile uint32_t *))FLG_CREATE)(p);
}

/* T_CTSK as LOSS card_task_create: {exinf, TA_HLNG|TA_DSNAME, entry, pri,
 * stksz, dsname[8], 0}. */
static int task_create(uint32_t entry) {
    volatile uint32_t d[8];
    d[0] = 0;
    d[1] = 0x41u;
    d[2] = entry;
    d[3] = WR_PRI;
    d[4] = WR_STACK;
    d[5] = 0x4C584D49u;             /* "IMXL" */
    d[6] = 0;
    d[7] = 0;
    int id = ((int (*)(volatile uint32_t *))TK_CRE_TSK)(d);
    if (id < 1) return id;
    return ((int (*)(int, uint32_t))TK_STA_TSK)(id, 0) == 0 ? id : -1;
}

/* `veneers`: six ARM veneers, 16 bytes apart, in wr.h's slot order.
 * `task_entry`: the ARM shim that loads the state and enters wr_task.
 * 0 = ready; anything else = do not hook (the sup releases its claims). */
int wr_card_init(wr_t *w, uint32_t task_entry, uint32_t veneers) {
    wr_fw fw;
    uint8_t *p = (uint8_t *)&fw;
    for (uint32_t i = 0; i < sizeof fw; i++) p[i] = 0;
    fw.dev_write = (int (*)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t))DEV_WRITE;
    fw.irq_off = (uint32_t (*)(void))IRQ_OFF;
    fw.irq_restore = (void (*)(uint32_t))IRQ_RESTORE;
    fw.flg_set = (int (*)(int, uint32_t))FLG_SET;
    fw.flg_wait = (int (*)(int, uint32_t, uint32_t, uint32_t *, int))FLG_WAIT;
    fw.dly = (void (*)(uint32_t))SLEEP_MS;
    fw.tick_us = (uint32_t (*)(void))TICK_US;
    uint32_t ven[6];
    for (uint32_t i = 0; i < 6; i++) ven[i] = veneers + 16u * i;
    int flag = flag_create();
    if (flag < 1) return 1;
    wr_init(w, &fw, flag, ven, WR_BLOCK, WR_SD_MAXDESC);
    w->task_id = task_create(task_entry);
    return w->task_id < 1 ? 2 : 0;
}
