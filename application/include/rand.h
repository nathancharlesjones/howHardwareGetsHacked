#ifndef RAND_H
#define RAND_H

#include <stdint.h>

void seed(uint32_t seed);
uint32_t rand(void);

#endif // RAND_H