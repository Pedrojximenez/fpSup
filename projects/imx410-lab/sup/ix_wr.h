/* IMXL fork of rec-core/writer/wr.h (ULWR, sha256 518de2ce...), 2026-10-20.
 * Only change: the sink (ix_cap) -- the writer either writes the block to the
 * card as ULWR does (IX_SD), copies it into DRAM the host lent us (IX_CAPTURE),
 * or drops it (IX_DISCARD).  Design: projects/imx410-lab/DESIGN.md §2.C.
 *
 * wr -- the native adapter between stock's file layer and our writer task.
 * Design: research/storage/notes/WRITER_LOCK_SCOPE.md §5-§7 (the six vol
 * pointers, the C063F140 hook, the late cookie, the stop drain).
 *
 * Every firmware call goes through wr_fw, so the same code runs on the host
 * against fakes (test_wr.py) and on the camera with the real addresses
 * (wr_card.S fills the table).  Every entry takes the wr_t: the card's
 * veneers load it, the firmware never sees it.
 *
 *   wr_installed  C063F220 returned 1 for `vol`: take the vol's arena pointers
 *   wr_send       C063F140 entry.  0 = handled; 1 = not ours, run stock
 *   wr_cb_*       what vol+0x4834..0x4848 point at while installed
 *   wr_task       the writer task's body (never returns)
 *   wr_take_start C063F220 entered (every aggregated take, ours or not)
 *   wr_late_frame C03A5348 after its write C069ADE0 returned: 1 = this frame
 *                 was written after the stop turned aggregation off, so stock
 *                 must complete it itself (the "mgr+0xD == 0" branch)
 */
#ifndef REC_CORE_WR_H
#define REC_CORE_WR_H
#include <stdint.h>
#include "bq.h"

#define WR_MAGIC      0x31525757u        /* "WWR1" */

/* vol fields (fp 5.02, WRITER_LOCK_SCOPE §1, FORMAT_CLUSTER_SIZE) */
#define V_DEV         0x0000u            /* device handle passed to C01EB790   */
#define V_HEAP_LBA    0x1458u            /* cluster heap, sectors (64-bit)     */
#define V_SECTOR      0x1460u            /* bytes per sector                   */
#define V_SPC         0x146Cu            /* sectors per cluster                */
#define V_THRESH      0x4828u
#define V_CB          0x4834u            /* cookie callback                    */
#define V_ACQ         0x4838u
#define V_ADD         0x483Cu
#define V_CKPT        0x4840u
#define V_RB          0x4844u
#define V_REL         0x4848u
#define V_ARENA       0x484Cu
#define V_NCOOKIE     0x4850u
#define V_COOKIES     0x4854u
#define V_CL          0x4A54u
#define V_BYTES       0x4A58u

#define WR_LR_STOP    0xC063F34Du        /* C063F310's bl C063F140 returns here */

/* C03A5348's frame (SRecFile): mgr = fp, node = r4 */
#define M_AGGREGATE   0x000Du            /* byte: completion comes from the vol */
#define N_STATE       0x1104u            /* 0xC handed to the FS, 0xD completed */
#define N_HANDED      0xCu

/* event flag bits */
#define WR_F_WORK     1u                 /* a block was sealed                  */
#define WR_F_FREE     2u                 /* a block became free                 */
#define WR_F_IDLE     4u                 /* nothing queued/writing/completing   */
#define TWF_ORW_BITCLR 0x21u

typedef struct {
    /* stock driver arena (the originals saved from the vol) */
    uint32_t (*drv_acquire)(void);
    int      (*drv_add)(uint32_t addr, uint32_t len);
    void     (*drv_release)(void);
    void     (*stock_cb)(uint32_t frame, uint32_t status);     /* C03A55D0 */
    /* device write C01EB790(dev, lba_lo, lba_hi, sectors, buf): 1 = ok */
    int      (*dev_write)(uint32_t dev, uint32_t lo, uint32_t hi, uint32_t n, uint32_t buf);
    uint32_t (*irq_off)(void);                                  /* C000EC14 */
    void     (*irq_restore)(uint32_t);                          /* C000EC24 */
    int      (*flg_set)(int id, uint32_t ptn);
    int      (*flg_wait)(int id, uint32_t ptn, uint32_t mode, uint32_t *out, int tmo_ms);
    void     (*dly)(uint32_t ms);
    uint32_t (*tick_us)(void);                                  /* C002B6E0 */
} wr_fw;

/* ---- the sink.  The host fills mode/nchunk/chunk while the camera is not
 * recording (cursor and counters zeroed first, mode last); the writer reads
 * mode once per block.  Capture memory is a list of chunks from the firmware
 * allocator (uncached alias), filled front to back with records:
 *
 *   ix_rec (32 B), then `bytes` bytes = what ULWR would have written at
 *   cluster `cl` (whole DNG files, cluster padded), then pad to 4.
 *
 * A record that does not fit whole is not stored (n_full++); its frames are
 * still completed with status 0, so the take goes on. */
enum { IX_SD = 0, IX_CAPTURE = 1, IX_DISCARD = 2 };
#define IX_MAX_CHUNK  32u
#define IX_REC_MAGIC  0x31525849u        /* "IXR1" */
#define IX_CAP_MAGIC  0x4C584D49u        /* "IMXL": the host finds the sink by it */

typedef struct { uint32_t addr, len; } ix_chunk;

typedef struct {
    uint32_t magic, seq, cl, bytes;      /* bytes: data after this header      */
    uint32_t ncookie, t_us, copy_us, nseg;
} ix_rec;

typedef struct {
    uint32_t magic;                      /* IX_CAP_MAGIC                        */
    uint32_t version;                    /* layout version, 1                   */
    /* host-written */
    uint32_t mode;
    uint32_t nchunk;
    ix_chunk chunk[IX_MAX_CHUNK];
    /* camera-written */
    uint32_t ci, coff;                   /* cursor: chunk index, offset in it   */
    uint32_t used;                       /* bytes stored, records included      */
    uint32_t n_rec, n_full, n_discard, n_sd;
    uint32_t t_first, t_last;            /* tick_us of the first/last record    */
    uint32_t copy_us, copy_max_us;       /* summed and worst per-block copy     */
} ix_cap;

/* Recognising the volume's driver by its saved acquire pointer. */
#define WR_SD_ACQ     0xC065F021u
#define WR_SSD_ACQ    0xC06702B9u
#define WR_SD_MAXDESC 0xC2F2E750u        /* bytes per ADMA descriptor           */

typedef struct {
    uint32_t magic;
    wr_fw    fw;
    int      flag;                       /* event flag id (> 0)                 */
    int      task_id;                    /* the writer task (wr_card.c)         */
    uint32_t veneer[6];                  /* cb, acq, add, ckpt, rb, rel (ours)  */
    uint32_t block_bytes;                /* batch size; rounded up to a cluster */
    uint32_t maxdesc_at;                 /* where the SD descriptor size lives  */
    /* the take */
    uint32_t vol;                        /* 0 when not installed                */
    uint32_t wvol;                       /* the writer's: kept after a restore  */
    uint32_t saved[6];                   /* stock +0x4834..+0x4848              */
    uint32_t sector_shift;
    uint32_t cur;                        /* block being written (writer only)   */
    /* counters (host tools read them) */
    uint32_t n_install, n_refuse, n_send, n_stock_send, n_chunk, n_acq_retry, n_dev_err,
             n_wait_free, n_drain, n_drain_timeout, n_late, n_late_direct, n_late_full,
             n_mismatch, last_status, n_late_frame;
    uint32_t ended_vol;                  /* the vol our stop restored; 0 at take start */
    ix_cap   cap;                        /* before q: a fixed offset for the host */
    bq_t     q;
} wr_t;

void     wr_init(wr_t *w, const wr_fw *fw, int flag, const uint32_t veneer[6],
                 uint32_t block_bytes, uint32_t maxdesc_at);
void     wr_installed(wr_t *w, uint32_t vol);
int      wr_send(wr_t *w, uint32_t vol, uint32_t lr);
void     wr_cb_cookie(wr_t *w, uint32_t frame, uint32_t status);
uint32_t wr_cb_acquire(wr_t *w);
int      wr_cb_add(wr_t *w, uint32_t addr, uint32_t len);
void     wr_cb_ckpt(wr_t *w);
void     wr_cb_rollback(wr_t *w);
void     wr_cb_release(wr_t *w);
/* One pass of the writer: write every queued block.  wr_task loops on it. */
void     wr_service(wr_t *w);
void     wr_task(wr_t *w);
void     wr_take_start(wr_t *w);
int      wr_late_frame(wr_t *w, uint32_t mgr, uint32_t node);

#endif
