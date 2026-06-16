#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include "rand.h"
#include "platform_impl.h"
#include "secrets.h"
#include "aes_cmac.h"
#include "aes.h"

static uint8_t g_state[16] = {0};
const uint8_t prng_key[16] = PRNG_KEY;

/* AES-ECB context used by the CMAC callback; key loaded once in main() */
static struct AES_ctx cmac_ctx;
/* AES-CMAC context storing the AES callback pointer */
static struct AES_CMAC_ctx aes_cmac_ctx;

static void aes_cmac_encrypt(uint8_t* data) {
  AES_ECB_encrypt(&cmac_ctx, data);
}

uint32_t prng_rand(void)
{
	static bool seeded = false;
	if(!seeded)
	{
		/* expand the key into AES round keys once; reused for every CMAC call */
		AES_init_ctx(&cmac_ctx, prng_key);
		/* provide the CMAC library with AES encryption callback function that will perform the actual AES encryption */
		AES_CMAC_init_ctx(&aes_cmac_ctx, (void*)&aes_cmac_encrypt);

		getPrngSeed(g_state);
		seeded = true;
	}
	uint8_t tmp[16] = {0};
	memcpy(tmp, g_state, 16);
	AES_CMAC_digest(&aes_cmac_ctx, tmp, 16, g_state);
	uint32_t ret = 0;
	memcpy(&ret, g_state, 4);
	return ret;
}