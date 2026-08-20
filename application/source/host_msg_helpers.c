#include <string.h>
#include <stdio.h>

#include "host_msg_helpers.h"
#include "messages.h"
#include "uart.h"

/**
 * @brief Send OK response to host
 */
void sendOK(const char *value)
{
  if (value)
  {
    uart_write(HOST_UART, (uint8_t *)"OK: ", 4);
    uart_write(HOST_UART, (uint8_t *)value, strlen(value));
    uart_write(HOST_UART, (uint8_t *)"\n", 1);
  }
  else
  {
    uart_write(HOST_UART, (uint8_t *)"OK\n", 3);
  }
}

/**
 * @brief Send ERROR response to host
 */
void sendError(const char *reason)
{
  char buf[128];
  snprintf(buf, sizeof(buf), "ERROR: %s\n", reason);
  uart_write(HOST_UART, (uint8_t *)buf, strlen(buf));
}

/**
 * @brief Fetch the board message log and send it to the host as a hex
 * string (the getBoardMsgLog test command on both car and fob - identical
 * on both, so kept here once instead of duplicated in car.c/fob.c).
 *
 * Locals rather than static/global: a compiler is free to size a whole
 * function's stack frame to the worst of its mutually-exclusive branches,
 * so this needs its own function - kept inline in a command dispatcher
 * that also handles other commands, it would tax every one of them for
 * stack space only this rarely-used command needs.
 *
 * Fixed-size (MAX_MSG_LOG_BYTES) rather than a VLA sized from
 * sizeofMsgLog()'s runtime value: a runtime-sized array is unbounded from
 * the compiler's perspective even when, as here, its actual size never
 * varies - and unbounded is unbounded whether or not it happens to also be
 * the biggest thing in its function.
 */
void sendMessageLogAsHex(void)
{
  if (sizeofMsgLog() > MAX_MSG_LOG_BYTES) { sendError("log buffer too small"); return; }

  uint8_t data[MAX_MSG_LOG_BYTES];
  memset(data, 0, sizeofMsgLog());
  getMessageLog(data);

  char hex[MAX_MSG_LOG_BYTES * 2 + 1];
  bytesToHex(data, sizeofMsgLog(), hex);

  sendOK(hex);
}

/**
 * @brief Convert bytes to hex string
 */
void bytesToHex(const uint8_t *bytes, size_t len, char *hex)
{
  const char hexChars[] = "0123456789abcdef";
  for (size_t i = 0; i < len; i++)
  {
    hex[i * 2] = hexChars[(bytes[i] >> 4) & 0x0F];
    hex[i * 2 + 1] = hexChars[bytes[i] & 0x0F];
  }
  hex[len * 2] = '\0';
}

/**
 * @brief Convert hex string to bytes
 * @return Number of bytes written, or -1 on error
 */
int hexToBytes(const char *hex, uint8_t *bytes, size_t maxLen)
{
  size_t hexLen = strlen(hex);
  if (hexLen % 2 != 0)
    return -1;

  size_t byteLen = hexLen / 2;
  if (byteLen > maxLen)
    return -1;

  for (size_t i = 0; i < byteLen; i++)
  {
    uint8_t hi, lo;

    if (hex[i * 2] >= '0' && hex[i * 2] <= '9')
      hi = hex[i * 2] - '0';
    else if (hex[i * 2] >= 'a' && hex[i * 2] <= 'f')
      hi = hex[i * 2] - 'a' + 10;
    else if (hex[i * 2] >= 'A' && hex[i * 2] <= 'F')
      hi = hex[i * 2] - 'A' + 10;
    else
      return -1;

    if (hex[i * 2 + 1] >= '0' && hex[i * 2 + 1] <= '9')
      lo = hex[i * 2 + 1] - '0';
    else if (hex[i * 2 + 1] >= 'a' && hex[i * 2 + 1] <= 'f')
      lo = hex[i * 2 + 1] - 'a' + 10;
    else if (hex[i * 2 + 1] >= 'A' && hex[i * 2 + 1] <= 'F')
      lo = hex[i * 2 + 1] - 'A' + 10;
    else
      return -1;

    bytes[i] = (hi << 4) | lo;
  }

  return (int)byteLen;
}