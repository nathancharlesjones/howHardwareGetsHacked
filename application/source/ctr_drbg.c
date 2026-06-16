/* ctr_drbg.c — CTR_DRBG per NIST SP 800-90A Rev.1 §10.2.1
 *
 * Configuration: AES-128, no derivation function, no additional input,
 *                no prediction resistance.
 *
 * Reference: https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-90ar1.pdf
 * Validated against NIST CAVS test vectors (CTR_DRBG, AES-128 no df,
 * PredictionResistance = False). */

#include "ctr_drbg.h"
#include "aes.h"
#include <string.h>

/* SP 800-90A Table 3, AES-128 no df:
 *   keylen  = 128 bits = 16 bytes
 *   outlen  = 128 bits = 16 bytes  (AES block size)
 *   seedlen = 256 bits = 32 bytes  (keylen + outlen) */
#define KEYLEN    16
#define OUTLEN    16
#define SEEDLEN   32  /* must equal KEYLEN + OUTLEN */

/* Maximum requests between reseeds: 2^48 per Table 3 for AES-128.
 * We cap lower so the counter fits in uint32_t and the caller is warned
 * well below any theoretical limit. On this platform a board reset
 * triggers re-instantiation, which resets the counter naturally. */
#define RESEED_INTERVAL  (1UL << 20)  /* ~1 million requests */

/* ---------------------------------------------------------------------------
 * Internal helpers
 * ------------------------------------------------------------------------- */

/* V = V + 1 (mod 2^128), big-endian as required by §10.2.1. */
static void v_increment(uint8_t V[OUTLEN])
{
    int i;
    for (i = OUTLEN - 1; i >= 0; i--) {
        if (++V[i] != 0) break;
    }
}

/* §10.2.1.2 CTR_DRBG_Update(provided_data, K, V)
 *
 * provided_data must be exactly SEEDLEN bytes.  Pass all-zeros when
 * called from Generate with no additional input — this is NOT a no-op;
 * it still rotates K and V to provide backtracking resistance. */
static void ctr_drbg_update(const uint8_t provided_data[SEEDLEN],
                             uint8_t K[KEYLEN], uint8_t V[OUTLEN])
{
    uint8_t temp[SEEDLEN];
    struct AES_ctx aes;
    int i;

    AES_init_ctx(&aes, K);

    /* Generate seedlen = 256 bits: two consecutive AES-ECB blocks. */
    v_increment(V);
    memcpy(temp, V, OUTLEN);
    AES_ECB_encrypt(&aes, temp);            /* temp[0..15]  = AES(K, V)   */

    v_increment(V);
    memcpy(temp + OUTLEN, V, OUTLEN);
    AES_ECB_encrypt(&aes, temp + OUTLEN);   /* temp[16..31] = AES(K, V+1) */

    /* XOR with provided_data. When provided_data is all-zeros this is
     * the identity operation on temp, but we still call Update so the
     * code path is unconditional and matches the spec exactly. */
    for (i = 0; i < SEEDLEN; i++) {
        temp[i] ^= provided_data[i];
    }

    /* New key = left half; new counter = right half. */
    memcpy(K, temp,          KEYLEN);
    memcpy(V, temp + KEYLEN, OUTLEN);
}

/* ---------------------------------------------------------------------------
 * Public API
 * ------------------------------------------------------------------------- */

/* §10.2.1.3 Instantiate (no derivation function).
 *
 * seed_material is used directly as the XOR input to the first Update call.
 * For AES-128 this must be exactly 32 bytes. */
void ctr_drbg_init(ctr_drbg_ctx_t *ctx, const uint8_t seed_material[SEEDLEN])
{
    memset(ctx->K, 0, KEYLEN);  /* Key  = 0^keylen  */
    memset(ctx->V, 0, OUTLEN);  /* V    = 0^outlen  */
    ctr_drbg_update(seed_material, ctx->K, ctx->V);
    ctx->reseed_counter = 1;
}

/* §10.2.1.5 Generate — no additional input, no prediction resistance.
 *
 * All n_bytes are generated with the current K before the post-generate
 * Update is called. This is the correct single-call semantics: output
 * blocks share a key, and the Update rotates K and V once at the end
 * to provide backtracking resistance. */
int ctr_drbg_generate_bytes(ctr_drbg_ctx_t *ctx, uint8_t *out, size_t n_bytes)
{
    static const uint8_t zeros[SEEDLEN] = {0};
    struct AES_ctx aes;
    size_t offset;

    if (n_bytes == 0 || n_bytes % OUTLEN != 0) return -2;  /* bad argument */
    if (ctx->reseed_counter > RESEED_INTERVAL)  return -1;  /* reseed needed */

    AES_init_ctx(&aes, ctx->K);

    /* Generate output blocks, all encrypted under the same key K. */
    for (offset = 0; offset < n_bytes; offset += OUTLEN) {
        v_increment(ctx->V);
        memcpy(out + offset, ctx->V, OUTLEN);
        AES_ECB_encrypt(&aes, out + offset);
    }

    /* Post-generate Update: rotates K and V for backtracking resistance.
     * Called once regardless of how many output blocks were generated.
     * This is mandatory — not optional — even with no additional input. */
    ctr_drbg_update(zeros, ctx->K, ctx->V);

    ctx->reseed_counter++;
    return 0;
}

/* §10.2.1.4 Reseed (no additional input). */
void ctr_drbg_reseed(ctr_drbg_ctx_t *ctx, const uint8_t entropy[SEEDLEN])
{
    ctr_drbg_update(entropy, ctx->K, ctx->V);
    ctx->reseed_counter = 1;
}

/* Convenience wrapper: generate one 32-bit value via Generate(128 bits). */
int ctr_drbg_generate(ctr_drbg_ctx_t *ctx, uint32_t *out)
{
    uint8_t block[OUTLEN];
    int ret = ctr_drbg_generate_bytes(ctx, block, sizeof(block));
    if (ret == 0) {
        memcpy(out, block, sizeof(uint32_t));
        memset(block, 0, sizeof(block));  /* scrub unused output bits */
    }
    return ret;
}
