/* Offline fixture: daemon main is never called.  Only drain_in() executes,
 * with every bulk transfer replaced by the mock below; no USB is accessed.
 */
#define FPSH_DIAGNOSTIC_FRAME_LOG 1
#define libusb_bulk_transfer mock_libusb_bulk_transfer
#define main fpshd_unused_daemon_entrypoint
#include "fpshd-diagnostic-v2.c"
#undef main
#undef libusb_bulk_transfer

static int mock_calls;
static int mock_bad_call;

int LIBUSB_CALL mock_libusb_bulk_transfer(libusb_device_handle *dev,
        unsigned char endpoint, unsigned char *data, int length,
        int *actual_length, unsigned int timeout)
{
    (void)dev;
    mock_calls++;
    if (endpoint != 0x82 || length != CMD_LINE_MAX || timeout != 20) {
        mock_bad_call = 1;
        *actual_length = 0;
        return LIBUSB_ERROR_INVALID_PARAM;
    }
    if (mock_calls == 1) {
        fpsh_frame frame;
        memset(&frame, 0, sizeof frame);
        memcpy(frame.magic, "FPSH", 4);
        frame.version = 1;
        frame.command = CMD_SHL;
        frame.sequence = 193;
        frame.checksum = crc32((const uint8_t *)&frame, sizeof frame);
        memcpy(data, &frame, sizeof frame);
        *actual_length = sizeof frame;
        return 0;
    }
    *actual_length = 0;
    return LIBUSB_ERROR_TIMEOUT;
}

int main(void)
{
    static const unsigned char short_bytes[12] = {
        0x0c, 0x00, 0x00, 0x00, 0x03, 0x00,
        0x03, 0x20, 0xc1, 0x00, 0x00, 0x00
    };
    errno = EDOM;
    diagnostic_frame_log(193, 0, 0, sizeof short_bytes, short_bytes);
    g_seq = 193;
    drain_in();
    if (mock_bad_call || mock_calls != 2 || errno != EDOM) return 1;
    /* Exercise the drain logger's cap independently of the loop. */
    unsigned char bytes[128];
    for (size_t i = 0; i < sizeof bytes; i++) bytes[i] = (unsigned char)i;
    diagnostic_drain_log(194, 7, 0, sizeof bytes, bytes);
    return errno == EDOM ? 0 : 2;
}
