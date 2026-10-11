#ifndef SIGMA_FP_V502_RAW_FALSE_COLOR_H
#define SIGMA_FP_V502_RAW_FALSE_COLOR_H

#include <stdint.h>

/* Read-only symbols confirmed in SIGMA fp firmware 5.02. */
enum {
    FP502_MOV_RAW_DONE_CALLBACK = 0xc0429f18u,
    FP502_MOV_PROCESS_SINGLETON = 0xc0425e40u,
    FP502_LIVEVIEW_RAW_MANAGER = 0xc0436590u,
    FP502_LIVEVIEW_RAW_SNAPSHOT = 0xc04370e8u,
    FP502_FALSE_COLOR_DRAW = 0xc057db98u,
    FP502_FALSE_COLOR_SETUP = 0xc057db40u,
    FP502_FALSE_COLOR_PALETTE = 0xc0d1b34cu,
    FP502_DRAW_VIEW_CREATE = 0xc0529bd8u,
    FP502_DRAW_PIXEL_ADDRESS = 0xc0529c80u,
    FP502_OSD_SINGLETON = 0xc0698d80u,
    FP502_IMX410_GAIN_COMPOSE = 0xc0323580u,
    FP502_IMX410_WRITE_GAIN_REGS = 0xc0323818u,
    FP502_IMX410_SELECT_HCG = 0xc03239c8u,
};

static inline uintptr_t fp502_sig_word_to_cached(uint32_t word_address)
{
    return (uintptr_t)0x40000000u + ((uintptr_t)word_address << 2);
}

#endif
