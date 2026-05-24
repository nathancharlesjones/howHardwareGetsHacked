#ifndef HOST_MSG_HELPERS
#define HOST_MSG_HELPERS

#include <stddef.h>
#include <stdint.h>

void sendOK(const char *value);
void sendError(const char *reason);
void bytesToHex(const uint8_t *bytes, size_t len, char *hex);
int hexToBytes(const char *hex, uint8_t *bytes, size_t maxLen);

#endif // HOST_MSG_HELPERS