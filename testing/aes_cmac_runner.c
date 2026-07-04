/* aes_cmac_runner.c — CLI test harness for tiny-AES-CMAC-c validation.
 *
 * Protocol (all hex):
 *   stdin:  line 1: 32 hex chars = 16 bytes AES-128 key
 *           line 2: message in hex, 0 to 2*MAX_MSG_BYTES chars (may be empty)
 *   stdout: one line, 32 hex chars = 16 bytes CMAC tag
 *
 * Exit 0 on success, non-zero on error. */

#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "aes.h"
#include "aes_cmac.h"

#define MAX_MSG_BYTES 512

static struct AES_ctx s_aes_ctx;

static void aes_encrypt_block(uint8_t *buf)
{
    AES_ECB_encrypt(&s_aes_ctx, buf);
}

static int hex_decode(const char *hex, uint8_t *out, size_t n_bytes)
{
    size_t i;
    for (i = 0; i < n_bytes; i++) {
        unsigned int byte;
        if (sscanf(hex + 2*i, "%02x", &byte) != 1) return -1;
        out[i] = (uint8_t)byte;
    }
    return 0;
}

static void hex_encode(const uint8_t *in, size_t n_bytes, char *out)
{
    size_t i;
    for (i = 0; i < n_bytes; i++) {
        sprintf(out + 2*i, "%02X", in[i]);
    }
    out[2 * n_bytes] = '\0';
}

int main(void)
{
    char line[2 * MAX_MSG_BYTES + 2];
    uint8_t key[16];
    uint8_t msg[MAX_MSG_BYTES];
    uint8_t tag[16];
    char hex_out[33];
    struct AES_CMAC_ctx cmac;
    size_t msg_len;

    if (!fgets(line, sizeof(line), stdin)) {
        fputs("error: no key input\n", stderr);
        return 1;
    }
    line[strcspn(line, "\r\n")] = '\0';
    if (strlen(line) != 32) {
        fprintf(stderr, "error: expected 32 hex chars for key, got %zu\n", strlen(line));
        return 1;
    }
    if (hex_decode(line, key, 16) != 0) {
        fputs("error: invalid key hex\n", stderr);
        return 1;
    }

    if (!fgets(line, sizeof(line), stdin)) {
        fputs("error: no message input\n", stderr);
        return 1;
    }
    line[strcspn(line, "\r\n")] = '\0';
    if (strlen(line) % 2 != 0 || strlen(line) / 2 > MAX_MSG_BYTES) {
        fprintf(stderr, "error: bad message length %zu\n", strlen(line));
        return 1;
    }
    msg_len = strlen(line) / 2;
    if (msg_len > 0 && hex_decode(line, msg, msg_len) != 0) {
        fputs("error: invalid message hex\n", stderr);
        return 1;
    }

    AES_init_ctx(&s_aes_ctx, key);
    AES_CMAC_init_ctx(&cmac, (void *)aes_encrypt_block);
    AES_CMAC_digest(&cmac, msg, (uint16_t)msg_len, tag);

    hex_encode(tag, sizeof(tag), hex_out);
    puts(hex_out);

    return 0;
}
