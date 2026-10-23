#include "qs_appearance.h"

int qs_background_set(QsAppearance *appearance, int alpha4) {
    if (!appearance || alpha4 < 0 || alpha4 > 15) return -1;
    if (appearance->background_alpha4 == alpha4) return 0;
    appearance->background_alpha4 = (uint8_t)alpha4;
    return 1;
}
unsigned qs_background_percent(const QsAppearance *appearance) {
    if (!appearance || appearance->background_alpha4 > 15) return 0;
    return (appearance->background_alpha4 * 100u + 7u) / 15u;
}
QsBackgroundPlan qs_background_plan(const QsAppearance *appearance) {
    QsBackgroundPlan plan = {QS_BG_OFF, 0, 0};
    if (!appearance || appearance->background_alpha4 > 15) return plan;
    plan.alpha4 = appearance->background_alpha4;
    if (plan.alpha4) {
        plan.mode = plan.alpha4 == 15 ? QS_BG_OPAQUE : QS_BG_BLEND;
        plan.fill_passes = 1;
    }
    return plan;
}
