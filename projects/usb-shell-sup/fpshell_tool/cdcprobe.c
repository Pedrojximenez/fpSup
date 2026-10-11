/* cdcprobe — 直接用 libusb 對 fp 的 CDC 除錯介面說話。
 *
 * `shl usb cdc` 之後相機以 VID 0x296B / PID 0x9998、產品名 "USB_DEBUG" 重新列舉,
 * 介面 0 = CDC-ACM comm(class 2), 介面 1 = CDC data(class 10, 兩個 bulk 端點)。
 * macOS 沒有自動掛序列驅動,但我們不需要 —— 資料介面就是 bulk,直接談。
 *
 * 目的:確認這條通道是不是韌體 shell 的主控台,以及它的吞吐量。
 *
 *   ./cdcprobe            送一個換行,讀回應
 *   ./cdcprobe "version"  送一行指令,讀回應
 */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "libusb.h"

#define VID 0x296B
#define PID 0x9998
#define EP_OUT 0x01
#define EP_IN  0x82

static void dump(const unsigned char *b, int n) {
    for (int i = 0; i < n; i++) putchar((b[i] >= 32 && b[i] < 127) || b[i] == '\n' || b[i] == '\r' ? b[i] : '.');
    putchar('\n');
}

int main(int argc, char **argv) {
    const char *cmd = argc > 1 ? argv[1] : "";
    libusb_context *ctx = NULL;
    if (libusb_init(&ctx)) { fprintf(stderr, "libusb_init failed\n"); return 1; }
    libusb_device_handle *h = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!h) { fprintf(stderr, "找不到 USB_DEBUG (VID %04x PID %04x)\n", VID, PID); return 1; }
    printf("USB_DEBUG 已開啟\n");
    for (int i = 0; i < 2; i++) {
        int rc = libusb_claim_interface(h, i);
        printf("  claim 介面 %d: %s\n", i, rc ? libusb_error_name(rc) : "OK");
    }
    /* CDC-ACM 握手:多數裝置在 DTR 被 assert 之前不會送資料。
     * SET_LINE_CODING(0x20) 帶 115200 8N1,再 SET_CONTROL_LINE_STATE(0x22) DTR|RTS。 */
    unsigned char lc[7] = { 0x00, 0xC2, 0x01, 0x00, 0x00, 0x00, 0x08 };  /* 115200, 1 stop, no parity, 8 bits */
    int cr = libusb_control_transfer(h, 0x21, 0x20, 0, 0, lc, 7, 1000);
    printf("  SET_LINE_CODING(115200 8N1): %s\n", cr < 0 ? libusb_error_name(cr) : "OK");
    cr = libusb_control_transfer(h, 0x21, 0x22, 0x0003, 0, NULL, 0, 1000);
    printf("  SET_CONTROL_LINE_STATE(DTR|RTS): %s\n", cr < 0 ? libusb_error_name(cr) : "OK");

    unsigned char buf[4096];
    int got = 0;
    /* 先把可能已排隊的輸出讀乾淨 */
    while (libusb_bulk_transfer(h, EP_IN, buf, sizeof buf, &got, 300) == 0 && got > 0) {
        printf("  [開場] "); dump(buf, got);
    }
    char line[256];
    snprintf(line, sizeof line, "%s\r\n", cmd);
    int sent = 0;
    int rc = libusb_bulk_transfer(h, EP_OUT, (unsigned char *)line, (int)strlen(line), &sent, 2000);
    printf("  送出 %d bytes: %s\n", sent, rc ? libusb_error_name(rc) : "OK");
    for (int i = 0; i < 6; i++) {
        got = 0;
        rc = libusb_bulk_transfer(h, EP_IN, buf, sizeof buf, &got, 1500);
        if (rc == 0 && got > 0) { printf("  [收到 %d] ", got); dump(buf, got); }
        else if (rc == LIBUSB_ERROR_TIMEOUT) { printf("  (逾時,無更多資料)\n"); break; }
        else { printf("  讀取: %s\n", libusb_error_name(rc)); break; }
    }
    for (int i = 0; i < 2; i++) libusb_release_interface(h, i);
    libusb_close(h); libusb_exit(ctx);
    return 0;
}
