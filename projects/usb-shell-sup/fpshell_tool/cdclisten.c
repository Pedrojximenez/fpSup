/* cdclisten — 只聽,不送。確認 fp 的 CDC 除錯介面會不會主動輸出。 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "libusb.h"
#define VID 0x296B
#define PID 0x9998
#define EP_IN 0x82
int main(int argc, char **argv) {
    int secs = argc > 1 ? atoi(argv[1]) : 10;
    libusb_context *ctx = NULL;
    if (libusb_init(&ctx)) return 1;
    libusb_device_handle *h = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!h) { fprintf(stderr, "找不到 USB_DEBUG\n"); return 1; }
    int rc = libusb_claim_interface(h, 1);
    printf("claim 資料介面: %s\n", rc ? libusb_error_name(rc) : "OK");
    if (rc) { libusb_close(h); return 1; }
    unsigned char buf[4096];
    int total = 0;
    for (int i = 0; i < secs; i++) {
        int got = 0;
        rc = libusb_bulk_transfer(h, EP_IN, buf, sizeof buf, &got, 1000);
        if (rc == 0 && got > 0) {
            total += got;
            printf("[%2ds +%4d] ", i, got);
            for (int j = 0; j < got; j++)
                putchar((buf[j] >= 32 && buf[j] < 127) || buf[j] == '\n' ? buf[j] : '.');
            printf("\n");
        } else if (rc != LIBUSB_ERROR_TIMEOUT) {
            printf("[%2ds] %s\n", i, libusb_error_name(rc));
            break;
        }
    }
    printf("總共收到 %d bytes\n", total);
    libusb_release_interface(h, 1);
    libusb_close(h); libusb_exit(ctx);
    return 0;
}
