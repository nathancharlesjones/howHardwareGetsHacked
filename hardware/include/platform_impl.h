#ifndef PLATFORM_IMPL_H
#define PLATFORM_IMPL_H

#include <stddef.h>

void load_flash(void* data, size_t size);
void save_flash(const void* data, size_t size);
void getPrngSeed(uint8_t * dest);

#endif // PLATFORM_IMPL_H