/* usbclaim — 只做 daemon 連線序列的一部分,用來二分「錄影變空白」的原因。
 *
 * fpshelld 連線時做三件事:開啟裝置 / claim 介面 1 / 一次 bulk IN 排掉開機 ZLP。
 * 實測「daemon 連著就不能正常錄影,斷開就恢復」,但不知道是哪一件造成的:
 *   - 只 claim 就壞 → 相機進入「已連接 PC」狀態,是政策問題
 *   - 要碰端點才壞 → 端點/DMA 資源衝突
 * 兩者的解法完全不同,所以先分清楚。
 *
 *   ./usbclaim open   N   只開啟裝置,不 claim,等 N 秒
 *   ./usbclaim claim  N   開啟 + claim 介面 1,不碰端點,等 N 秒
 *   ./usbclaim drain  N   開啟 + claim + 一次 bulk IN(跟 daemon 相同),等 N 秒
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "libusb.h"

#define VID 0x1003
#define PID 0xc432
#define EP_IN 0x84

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "claim";
    unsigned secs = argc > 2 ? (unsigned)strtoul(argv[2], NULL, 10) : 60;
    libusb_context *ctx = NULL;
    if (libusb_init(&ctx) != 0) { fprintf(stderr, "libusb_init failed\n"); return 1; }
    libusb_device_handle *h = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!h) { fprintf(stderr, "找不到相機 (vendor 介面沒出現?)\n"); return 1; }
    printf("裝置已開啟\n"); fflush(stdout);

    if (strcmp(mode, "open") != 0) {
        int rc = libusb_claim_interface(h, 1);
        if (rc != 0) { fprintf(stderr, "claim 失敗: %s\n", libusb_error_name(rc)); return 1; }
        printf("介面 1 已 claim\n"); fflush(stdout);
    }
    if (strcmp(mode, "drain") == 0) {
        unsigned char b = 0; int got = 0;
        int rc = libusb_bulk_transfer(h, EP_IN, &b, 1, &got, 1000);
        printf("bulk IN: %s transferred=%d\n", libusb_error_name(rc), got); fflush(stdout);
    }
    printf("保持此狀態 %u 秒 —— 請在這段期間錄影\n", secs); fflush(stdout);
    sleep(secs);
    printf("釋放\n");
    if (strcmp(mode, "open") != 0) libusb_release_interface(h, 1);
    libusb_close(h); libusb_exit(ctx);
    return 0;
}
