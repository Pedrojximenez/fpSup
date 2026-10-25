/* Test only (test_ui_v4.py): fpSup/fpsup-ui's functions, reachable from the
 * test through svc->find().  A sup that #includes the library as any sup
 * would; each function is provided under its own id ("FPU0" ..). */
#include "sloader4.h"
#include "fpsup_ui.c"

static uint32_t p_text(const void *ui, uint32_t i) { return (uint32_t)(uintptr_t)fpui_text(ui, i); }
static uint32_t p_first(const void *ui, uint32_t i) { return fpui_first(ui, i); }
static uint32_t p_set(const void *ui, uint32_t i, uint32_t v) { fpui_set(ui, i, v); return 0; }
static uint32_t p_watch(const void *ui, uint32_t i, uint32_t fn)
{
    return (uint32_t)fpui_watch(ui, i, (uint32_t (*)(uintptr_t))(uintptr_t)fn);
}
static uint32_t p_install(const struct sl_svc *svc, const void *ui) { return fpui_install(svc, ui); }
static uint32_t p_read(const struct sl_svc *svc, const char *path) { return (uint32_t)(uintptr_t)fpui_read(svc, path); }

int sup_entry(void *block, const struct sl_svc *svc, const char *path)
{
    (void)block; (void)path;
    svc->provide(svc, 0x30555046u, (void *)p_text);       /* "FPU0" */
    svc->provide(svc, 0x31555046u, (void *)p_first);
    svc->provide(svc, 0x32555046u, (void *)p_set);
    svc->provide(svc, 0x33555046u, (void *)p_watch);
    svc->provide(svc, 0x34555046u, (void *)p_install);
    svc->provide(svc, 0x35555046u, (void *)p_read);
    return SL_KEEP;
}
