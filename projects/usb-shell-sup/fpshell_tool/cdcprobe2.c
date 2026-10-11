/* cdcprobe2 — 更仔細地探測 fp 的 CDC 除錯介面。
 *
 * 前一版的問題:反覆 claim/release 之後端點可能 stall,而且只試了一種輸入。
 * 這版:先 clear halt,再依序試多種輸入,每次等久一點。
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include "libusb.h"
#define VID 0x296B
#define PID 0x9998
#define EP_OUT 0x01
#define EP_IN  0x82

static libusb_device_handle *h;

static int drain(int ms, const char *tag) {
    unsigned char buf[8192]; int total = 0, got, rc;
    while ((rc = libusb_bulk_transfer(h, EP_IN, buf, sizeof buf, &got, ms)) == 0 && got > 0) {
        printf("    [%s +%d] ", tag, got);
        for (int i = 0; i < got && i < 200; i++)
            putchar((buf[i] >= 32 && buf[i] < 127) || buf[i] == '\n' ? buf[i] : '.');
        printf("\n");
        total += got;
    }
    if (rc != 0 && rc != LIBUSB_ERROR_TIMEOUT) printf("    [%s] %s\n", tag, libusb_error_name(rc));
    return total;
}

int main(void) {
    if (libusb_init(NULL)) return 1;
    h = libusb_open_device_with_vid_pid(NULL, VID, PID);
    if (!h) { fprintf(stderr, "找不到 USB_DEBUG\n"); return 1; }
    printf("已開啟 USB_DEBUG\n");
    for (int i = 0; i < 2; i++) libusb_claim_interface(h, i);
    printf("clear halt OUT: %s\n", libusb_error_name(libusb_clear_halt(h, EP_OUT)));
    printf("clear halt IN : %s\n", libusb_error_name(libusb_clear_halt(h, EP_IN)));
    drain(500, "殘留");

    const char *tries[] = { "\r", "\n", "\r\n", "help\r\n", "version\r\n", "?\r\n" };
    for (unsigned t = 0; t < sizeof tries / sizeof *tries; t++) {
        int sent = 0;
        int rc = libusb_bulk_transfer(h, EP_OUT, (unsigned char *)tries[t],
                                      (int)strlen(tries[t]), &sent, 2000);
        printf("送 %-12s → %s (%d bytes)\n",
               tries[t][0] == '\r' && strlen(tries[t]) <= 2 ? "<CR/LF>" : tries[t],
               rc ? libusb_error_name(rc) : "OK", sent);
        int got = drain(1200, "回應");
        if (got) printf("  ★ 有回應,共 %d bytes\n", got);
    }
    for (int i = 0; i < 2; i++) libusb_release_interface(h, i);
    libusb_close(h); libusb_exit(NULL);
    return 0;
}
