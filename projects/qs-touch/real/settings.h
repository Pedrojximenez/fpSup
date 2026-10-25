#ifndef QSN_SETTINGS_H
#define QSN_SETTINGS_H
#include <stdint.h>

/* Called only on the native QS GUI thread. Names are resident strings owned
 * by the SUP. Never register, subscribe to, or manufacture a stock variable. */
struct qsn_native {
    uintptr_t app;
    uint32_t (*lookup)(uintptr_t, const char *, uintptr_t *);
    uint32_t (*notify)(uintptr_t, uint32_t, uint32_t, const uint32_t *);
};

static int qsn_read(const struct qsn_native *api, const char *name, uint32_t *value)
{
    uintptr_t desc = 0;
    if (!api || !api->app || !name || !value ||
        api->lookup(api->app, name, &desc) || !desc || (desc & 3u)) return 0;
    const volatile uint32_t *p = (const volatile uint32_t *)desc;
    if (p[0] != 0u) return 0;
    *value = p[2];
    return 1;
}

/* A notifying write reaches UicGuiMenuQs's ORIGINAL subscriber, including
 * Res-Custom's existing converter/commit hooks. A queued display post is not
 * a setting change. Readback is mandatory and is kept separate from acceptance
 * of the requested value: the native normalizer may change it. */
static int qsn_apply(const struct qsn_native *api, const char *name,
                     uint32_t requested, uint32_t count, uint32_t *readback)
{
    uint32_t before;
    if (!count || requested >= count || !qsn_read(api, name, &before)) return 0;
    if (before != requested) {
        uint32_t assignment[3] = {0u, (uint32_t)(uintptr_t)name, requested};
        if (api->notify(api->app, 0u, 1u, assignment)) return 0;
    }
    return qsn_read(api, name, readback);
}
#endif
