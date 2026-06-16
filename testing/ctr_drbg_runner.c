/* ctr_drbg_runner.c — CLI test harness for NIST CAVS validation.
 *
 * Protocol (all hex, uppercase):
 *   stdin:  line 1: 64 hex chars = 32 bytes EntropyInput
 *           line 2: 64 hex chars = 32 bytes EntropyInputReseed  (optional)
 *   stdout: two lines, each 128 hex chars = 64 bytes ReturnedBits
 *           (matching CAVS ReturnedBitsLen = 512)
 *
 * If a second line is present, ctr_drbg_reseed() is called before the first
 * Generate call, matching the NIST CAVS "no prediction resistance" protocol
 * (Instantiate → Reseed → Generate → Generate, compare second output).
 *
 * Exit 0 on success, non-zero on error. */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "ctr_drbg.h"

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
    char line[128 + 2];   /* 64 hex chars + newline + null */
    uint8_t seed[32];
    uint8_t gen1[64], gen2[64];
    char hex_out[128 + 1];
    ctr_drbg_ctx_t ctx;

    /* Read entropy input: exactly 64 hex chars. */
    if (!fgets(line, sizeof(line), stdin)) {
        fputs("error: no input\n", stderr);
        return 1;
    }
    /* Strip newline. */
    line[strcspn(line, "\r\n")] = '\0';
    if (strlen(line) != 64) {
        fprintf(stderr, "error: expected 64 hex chars, got %zu\n", strlen(line));
        return 1;
    }
    if (hex_decode(line, seed, 32) != 0) {
        fputs("error: invalid hex\n", stderr);
        return 1;
    }

    /* Instantiate. seed_material = EntropyInput (32 bytes, no nonce,
     * no personalization string — correct for AES-128 no df). */
    ctr_drbg_init(&ctx, seed);
    memset(seed, 0, sizeof(seed));

    /* Optional reseed: if a second line of input is present, apply it before
     * any Generate call.  This matches the NIST CAVS "no prediction
     * resistance" protocol: Instantiate → Reseed → Generate → Generate. */
    if (fgets(line, sizeof(line), stdin)) {
        uint8_t reseed[32];
        line[strcspn(line, "\r\n")] = '\0';
        if (strlen(line) == 64 && hex_decode(line, reseed, 32) == 0) {
            ctr_drbg_reseed(&ctx, reseed);
            memset(reseed, 0, sizeof(reseed));
        }
    }

    /* First Generate(512 bits). */
    if (ctr_drbg_generate_bytes(&ctx, gen1, sizeof(gen1)) != 0) {
        fputs("error: generate 1 failed\n", stderr);
        return 1;
    }

    /* Second Generate(512 bits). */
    if (ctr_drbg_generate_bytes(&ctx, gen2, sizeof(gen2)) != 0) {
        fputs("error: generate 2 failed\n", stderr);
        return 1;
    }

    hex_encode(gen1, sizeof(gen1), hex_out);
    puts(hex_out);
    hex_encode(gen2, sizeof(gen2), hex_out);
    puts(hex_out);

    return 0;
}
