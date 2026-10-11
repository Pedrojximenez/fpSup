/* Offline fixture only.  The renamed daemon entrypoint is never called.
 * No libusb_init, device operation, socket, or daemon startup is executed.
 */
#define FPSH_DIAGNOSTIC_FRAME_LOG 1
#define main fpshd_unused_daemon_entrypoint
#include "fpshd-diagnostic.c"
#undef main

int main(void)
{
    unsigned char bytes[64];
    for (size_t i = 0; i < sizeof bytes; i++) bytes[i] = (unsigned char)i;
    errno = EDOM;
    diagnostic_frame_log(700, 0, 0, 12, bytes);
    if (errno != EDOM) return 1;
    diagnostic_frame_log(701, 1, -7, 0, NULL);
    if (errno != EDOM) return 2;
    diagnostic_frame_log(702, 2, -7, 64, bytes);
    if (errno != EDOM) return 3;
    diagnostic_frame_log(703, 3, -1, 100, bytes);
    if (errno != EDOM) return 4;
    diagnostic_frame_log(704, 4, -1, -1, NULL);
    return errno == EDOM ? 0 : 5;
}
