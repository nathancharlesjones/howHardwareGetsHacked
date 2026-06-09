#include <stdint.h>
#include "rand.h"

static uint32_t g_seed = 0;

void seed(uint32_t seed)
{
	g_seed = seed;
}

uint32_t rand(void)
{
	return g_seed++;
}