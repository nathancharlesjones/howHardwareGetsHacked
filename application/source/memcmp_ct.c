#include <stddef.h>
#include <stdint.h>

int memcmp_ct(const void *ptr1, const void *ptr2, size_t num)
{
  int diff = 0;
  for(size_t idx = 0; idx < num; idx++)
  {
    uint8_t byte1 = ((const uint8_t*)ptr1)[idx];
    uint8_t byte2 = ((const uint8_t*)ptr2)[idx];
    diff |= (byte1 ^ byte2);
  }
  return diff;
}
