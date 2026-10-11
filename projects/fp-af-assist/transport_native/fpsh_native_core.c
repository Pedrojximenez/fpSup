#include "fpsh_native_core.h"

static uint16_t get16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void put16(uint8_t *p, uint16_t n)
{
    p[0] = (uint8_t)n;
    p[1] = (uint8_t)(n >> 8);
}

static void put32(uint8_t *p, uint32_t n)
{
    p[0] = (uint8_t)n;
    p[1] = (uint8_t)(n >> 8);
    p[2] = (uint8_t)(n >> 16);
    p[3] = (uint8_t)(n >> 24);
}

static uint32_t frame_crc(const uint8_t *p)
{
    uint32_t c = 0xffffffffu;
    for (uint32_t i = 0; i < FPSH_FRAME_SIZE; ++i) {
        c ^= (i >= 16u && i < 20u) ? 0u : p[i];
        for (uint32_t bit = 0; bit < 8u; ++bit)
            c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
    }
    return ~c;
}

static int fail(struct fpsh_native_state *s, int reason)
{
    if (s->phase != FPSH_FAULTED) s->fault = reason;
    s->phase = FPSH_FAULTED;
    return reason;
}

int fpsh_native_init(struct fpsh_native_state *s, uint32_t generation)
{
    if (!s || s->magic != 0u || generation == 0u) return FPSH_BAD_STATE;
    /* Zero initialization is the loader's obligation; do not silently repair
     * a partially populated state or reset a persisted sequence. */
    if (s->phase || s->generation || s->last_sequence || s->fault ||
        s->version_calls || s->commands_completed || s->frames_sent)
        return FPSH_BAD_STATE;
    for (uint32_t i = 0; i < FPSH_REPLY_CAP; ++i) s->output[i] = 0;
    for (uint32_t i = 0; i < FPSH_FRAME_SIZE; ++i) s->reply[i] = 0;
    s->magic = FPSH_STATE_MAGIC;
    s->generation = generation;
    s->phase = FPSH_READY;
    return FPSH_OK;
}

void fpsh_native_invalidate(struct fpsh_native_state *s)
{
    if (s && s->magic == FPSH_STATE_MAGIC) (void)fail(s, FPSH_INVALIDATED);
}

static int still_active(struct fpsh_native_state *s, uint32_t generation)
{
    return s->magic == FPSH_STATE_MAGIC && s->phase == FPSH_ACTIVE &&
           s->generation == generation;
}

static void prepare_reply(struct fpsh_native_state *s, uint8_t command,
                          uint32_t sequence, uint32_t offset, uint32_t count,
                          uint16_t more, uint16_t status)
{
    for (uint32_t i = 0; i < FPSH_FRAME_SIZE; ++i) s->reply[i] = 0;
    s->reply[0] = 'F'; s->reply[1] = 'P';
    s->reply[2] = 'S'; s->reply[3] = 'H';
    s->reply[4] = 1; s->reply[5] = command;
    put16(s->reply + 6, more);
    put32(s->reply + 8, sequence);
    put16(s->reply + 12, (uint16_t)count);
    put16(s->reply + 14, status);
    for (uint32_t i = 0; i < count; ++i) s->reply[20u + i] = s->output[offset + i];
    put32(s->reply + 16, frame_crc(s->reply));
}

int fpsh_native_process(struct fpsh_native_state *s,
                        const struct fpsh_native_ops *ops,
                        const uint8_t *packet, uint32_t length,
                        int complete_transfer, uint32_t generation)
{
    uint8_t input[FPSH_FRAME_SIZE];
    uint32_t sequence, payload, used = 0, offset = 0;
    uint16_t status = FPSH_STATUS_OK;
    int result = FPSH_OK;
    static const uint8_t version[] = "shl version";

    if (!s || s->magic != FPSH_STATE_MAGIC) return FPSH_BAD_STATE;
    if (s->phase == FPSH_FAULTED) return FPSH_BAD_STATE;
    if (s->phase == FPSH_ACTIVE) return fail(s, FPSH_REENTRANT);
    if (s->phase != FPSH_READY || !ops || !ops->send_frame)
        return fail(s, FPSH_BAD_STATE);
    if (generation != s->generation) return fail(s, FPSH_INVALIDATED);
    if (!packet || length != FPSH_FRAME_SIZE || complete_transfer != 1)
        return fail(s, FPSH_BOUNDARY);
    /* Snapshot input before callbacks or reply writes; the caller must ensure
     * that the native producer cannot mutate it during this bounded copy. */
    for (uint32_t i = 0; i < FPSH_FRAME_SIZE; ++i) input[i] = packet[i];
    if (input[0] != 'F' || input[1] != 'P' || input[2] != 'S' ||
        input[3] != 'H' || input[4] != 1)
        return fail(s, FPSH_FORMAT);
    if (get32(input + 16) != frame_crc(input)) return fail(s, FPSH_CRC);
    payload = get16(input + 12);
    if (get16(input + 6) != 0 || get16(input + 14) != 0 || payload >= FPSH_PAYLOAD_SIZE)
        return fail(s, FPSH_FORMAT);
    for (uint32_t i = 0; i < payload; ++i)
        if (input[20u + i] < 0x20u || input[20u + i] > 0x7eu)
            return fail(s, FPSH_FORMAT);
    for (uint32_t i = payload; i < FPSH_PAYLOAD_SIZE; ++i)
        if (input[20u + i] != 0) return fail(s, FPSH_FORMAT);
    sequence = get32(input + 8);
    if (s->last_sequence == 0xffffffffu || sequence != s->last_sequence + 1u)
        return fail(s, FPSH_SEQUENCE);

    s->last_sequence = sequence;
    s->phase = FPSH_ACTIVE;
    for (uint32_t i = 0; i < FPSH_REPLY_CAP; ++i) s->output[i] = 0;
    if (input[5] == 1u && payload == 0u) {
        s->output[0] = 'p'; s->output[1] = 'o';
        s->output[2] = 'n'; s->output[3] = 'g';
        used = 4;
    } else {
        int allowed = input[5] == 3u && payload == sizeof(version) - 1u;
        for (uint32_t i = 0; allowed && i < sizeof(version) - 1u; ++i)
            if (input[20u + i] != version[i]) allowed = 0;
        if (!allowed) {
            status = FPSH_STATUS_DENIED;
            result = FPSH_DENIED;
        } else if (!ops->version) {
            status = FPSH_STATUS_COMMAND_FAILED;
            result = FPSH_COMMAND_FAILED;
        } else {
            ++s->version_calls;
            int rc = ops->version(ops->opaque, s->output, FPSH_REPLY_CAP, &used);
            if (!still_active(s, generation)) return fail(s, FPSH_INVALIDATED);
            if (rc != 0 || used == 0u || used > FPSH_REPLY_CAP) {
                used = 0;
                status = FPSH_STATUS_COMMAND_FAILED;
                result = FPSH_COMMAND_FAILED;
            }
        }
    }
    if (result == FPSH_OK) ++s->commands_completed;
    /* At most ceil(128 / 44) = 3 frames. One empty frame reports a denied or
     * failed command. No send failure can cause another execution or send. */
    do {
        uint32_t count = used - offset;
        if (count > FPSH_PAYLOAD_SIZE) count = FPSH_PAYLOAD_SIZE;
        prepare_reply(s, input[5], sequence, offset, count,
                      (uint16_t)(offset + count < used), status);
        int rc = ops->send_frame(ops->opaque, s->reply, FPSH_FRAME_SIZE);
        if (!still_active(s, generation)) return fail(s, FPSH_INVALIDATED);
        if (rc != 0) return fail(s, FPSH_SEND_FAILED);
        ++s->frames_sent;
        offset += count;
    } while (offset < used);
    if (result != FPSH_OK) return fail(s, result);
    s->phase = FPSH_READY;
    return FPSH_OK;
}
