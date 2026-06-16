/* ctr_drbg.h — CTR_DRBG per NIST SP 800-90A Rev.1
 * Configuration: AES-128, no derivation function */
#pragma once
#include <stdint.h>
#include <stddef.h>

typedef struct {
    uint8_t  K[16];           /* AES-128 key              */
    uint8_t  V[16];           /* 128-bit counter           */
    uint32_t reseed_counter;
} ctr_drbg_ctx_t;

/* Instantiate.
 *
 * seed_material must be exactly 32 bytes (seedlen = keylen + outlen for
 * AES-128). Provide your 16-byte entropy output followed by 16 zero bytes
 * if you only have 128 bits of entropy — sufficient for 128-bit security
 * per Table 3.
 *
 * Scrub seed_material from the stack after this call. */
void ctr_drbg_init(ctr_drbg_ctx_t *ctx, const uint8_t seed_material[32]);

/* Generate — multi-block form used for NIST CAVS validation.
 *
 * Fills `out` with `n_bytes` of pseudorandom output in a single logical
 * Generate call: all output blocks are produced with the same key, and
 * the post-generate Update is called once at the end. This matches the
 * CAVS test format (ReturnedBitsLen = 512 = 4 blocks of 128 bits).
 *
 * n_bytes must be a positive multiple of 16.
 *
 * Returns  0 on success.
 * Returns -1 when the reseed limit is reached; call ctr_drbg_init again
 *           with fresh entropy. On this platform a board reset triggers
 *           re-instantiation, naturally resetting the counter. */
int ctr_drbg_generate_bytes(ctr_drbg_ctx_t *ctx, uint8_t *out, size_t n_bytes);

/* §10.2.1.4 Reseed (no additional input).
 *
 * entropy must be exactly 32 bytes.  Resets the reseed counter so the
 * generator can produce another RESEED_INTERVAL outputs before needing
 * to reseed again. */
void ctr_drbg_reseed(ctr_drbg_ctx_t *ctx, const uint8_t entropy[32]);

/* Convenience wrapper: produce one 32-bit pseudorandom value.
 *
 * Internally performs a full Generate(128 bits) and returns the first
 * 4 bytes. The remaining 96 bits are discarded; they are not reused on
 * the next call. This matches the spec's requirement that output not be
 * buffered across Generate calls at the application layer. */
int ctr_drbg_generate(ctr_drbg_ctx_t *ctx, uint32_t *out);
