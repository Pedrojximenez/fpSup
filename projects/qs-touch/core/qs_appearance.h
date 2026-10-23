#ifndef FP_QS_APPEARANCE_H
#define FP_QS_APPEARANCE_H
#include <stdint.h>

/* ARGB4444 has 16 alpha levels. These are draw plans, not hardware layers. */
typedef struct { uint8_t background_alpha4; } QsAppearance;
typedef enum { QS_BG_OFF, QS_BG_BLEND, QS_BG_OPAQUE } QsBackgroundMode;
typedef struct { QsBackgroundMode mode; uint8_t alpha4, fill_passes; } QsBackgroundPlan;
int qs_background_set(QsAppearance *appearance, int alpha4);
unsigned qs_background_percent(const QsAppearance *appearance);
QsBackgroundPlan qs_background_plan(const QsAppearance *appearance);
#endif
