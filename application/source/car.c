/**
 * @file carFirmware.c
 * @author Frederich Stine
 * @brief eCTF Car Example Design Implementation
 * @date 2023
 *
 * This source file is part of an example system for MITRE's 2023 Embedded
 * System CTF (eCTF). This code is being provided only for educational purposes
 * for the 2023 MITRE eCTF competition, and may not meet MITRE standards for
 * quality. Use this code at your own risk!
 *
 * @copyright Copyright (c) 2023 The MITRE Corporation
 */

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>
#include <stddef.h>
#include <stdlib.h>

#include "secrets.h"
#include "messages.h"
#include "dataFormats.h"
#include "uart.h"
#include "platform.h"
#include "host_msg_helpers.h"
#include "aes_cmac.h"
#include "aes.h"
#include "ctr_drbg.h"

/*** Macros ***/
#define MAX_CMD_LEN 1040

// sendBoardMsg's own hex-decode scratch buffer (see below): sized to carry a
// full MESSAGE_PACKET regardless of MAX_MSG_LEN, so this TEST_BUILD-only
// command can inject realistic oversized/malicious payloads for security
// testing instead of being artificially capped by the real wire-message size.
#define TEST_SENDBOARDMSG_BUF_LEN 257  // 1 magic + 1 message_len + 255 max payload

/*** Function definitions ***/
// Core functions - unlockCar and startCar
void unlockCar(void);

/* AES-ECB context used by the CMAC callback; key loaded once in main() */
static struct AES_ctx cmac_ctx;
/* AES-CMAC context storing the AES callback pointer */
static struct AES_CMAC_ctx aes_cmac_ctx;

static ctr_drbg_ctx_t prng_ctx;

static void aes_cmac_encrypt(uint8_t* data) {
  AES_ECB_encrypt(&cmac_ctx, data);
}

// Helper functions - sending ack messages
void sendAckSuccess(void);
void sendAckFailure(void);

// Command processing
void processHostCommand(const char *cmd);

// Declare const variables
const uint8_t unlock_key[16] = UNLOCK_KEY;
const char car_id[11] = CAR_ID;

// State variables
static bool carLocked = true;
static uint32_t unlockCount = 0;
static uint8_t last_feature_info[NUM_FEATURES+1] = {0,1,2,3};

static void initCar(void)
{
  uint8_t seed[32] = {0};
  getPrngSeed(seed);
  ctr_drbg_init(&prng_ctx, seed);

  carLocked = true;
  unlockCount = 0;
}

/**
 * @brief Main function for the car example
 *
 * Initializes the RF module and waits for a successful unlock attempt.
 * If successful prints out the unlock flag.
 */
int main(int argc, char **argv)
{
  initHardware_car(argc, argv);

  /* expand the key into AES round keys once; reused for every CMAC call */
  AES_init_ctx(&cmac_ctx, unlock_key);
  /* provide the CMAC library with AES encryption callback function that will perform the actual AES encryption */
  AES_CMAC_init_ctx(&aes_cmac_ctx, (void*)&aes_cmac_encrypt);

  initCar();

  // Signal ready to host
  uart_write(HOST_UART, (uint8_t *)"OK: started\n", 12);

  // Buffer for host commands
  char cmdBuffer[MAX_CMD_LEN];
  uint8_t cmdIndex = 0;

  while (true)
  {
    // Check for host commands (non-blocking)
    if (uart_avail(HOST_UART))
    {
      uint8_t c = (uint8_t)uart_readb(HOST_UART);

      if (c == '\n' || c == '\r')
      {
        if (cmdIndex > 0)
        {
          cmdBuffer[cmdIndex] = '\0';
          processHostCommand(cmdBuffer);
          cmdIndex = 0;
        }
      }
      else if ( (cmdIndex < MAX_CMD_LEN - 1) && (isalnum(c) || ' ' == c) )
      {
        cmdBuffer[cmdIndex++] = c;
      }
    }

    // Check for board messages (blocking)
    if (uart_avail(BOARD_UART)) unlockCar();
  }
}

/**
 * @brief Process a command received from the host
 */
void processHostCommand(const char *cmd)
{
#ifdef TEST_BUILD
  // Test command: isLocked
  if (strcmp(cmd, "isLocked") == 0)
  {
    sendOK(carLocked ? "1" : "0");
    return;
  }

  // Test command: getUnlockCount
  if (strcmp(cmd, "getUnlockCount") == 0)
  {
    char buf[16];
    snprintf(buf, sizeof(buf), "%lu", (unsigned long)unlockCount);
    sendOK(buf);
    return;
  }

  // Test command: sendRawBoardMsg <hex>
  if (strncmp(cmd, "sendBoardMsg ", 13) == 0)
  {
    uint8_t raw[TEST_SENDBOARDMSG_BUF_LEN];
    int len = hexToBytes(cmd + 13, raw, sizeof(raw));
    if (len < 2) { sendError("invalid hex"); return; }
    MESSAGE_PACKET msg;
    msg.magic = raw[0];
    msg.message_len = raw[1];
    msg.buffer = raw + 2;

    send_board_message(&msg);
    
    sendOK(NULL);
    return;
  }

  // Test command: getBoardMsgLog
  if (strcmp(cmd, "getBoardMsgLog") == 0)
  {
    uint8_t data[sizeofMsgLog()];
    memset(data, 0, sizeof(data));
    getMessageLog(data);

    char hex[sizeof(data) * 2 + 1];
    bytesToHex(data, sizeof(data), hex);

    sendOK(hex);
    return;
  }

  // Test command: reset (factory reset)
  if (strcmp(cmd, "reset") == 0)
  {
    initCar();
    sendOK(NULL);
    return;
  }

  // Test command: restart (warm restart)
  if (strcmp(cmd, "restart") == 0)
  {
    sendOK(NULL);
    restart(); // On hardware this reboots and never returns; sim's stub does return
    return;
  }

  // Test command: getEntropyDescription
  if (strcmp(cmd, "getEntropyDescription") == 0)
  {
    sendOK(getEntropyDescription());
    return;
  }

  // Test command: getEntropySamples
  if (strncmp(cmd, "getEntropySamples ", 18) == 0)
  {
    uint8_t num_samples = atoi(cmd + 18);

    // Fixed at the worst-case row width across all platforms (see
    // getEntropyDescription()/getEntropySamples() in hardware/*/source/*.c)
    // so this never needs to be a VLA; num_samples is a uint8_t, so this is
    // also the hard upper bound on how large a request can ever be.
    #define MAX_ENTROPY_ROW_BYTES 10
    uint8_t samples[255*MAX_ENTROPY_ROW_BYTES] = {0};
    uint16_t bytes = getEntropySamples(num_samples, samples);

    char hex[sizeof(samples)*2+1] = {0};
    bytesToHex(samples, bytes, hex);
    sendOK(hex);
    return;
  }

  // Test command: getFeatures
  if (strcmp(cmd, "getFeatures") == 0)
  {
    if( !carLocked )
    {
      char hex[sizeof(last_feature_info)*2+1] = {0};
      bytesToHex(last_feature_info, sizeof(last_feature_info), hex);
      sendOK(hex);
    }
    else sendError("Car has not been unlocked yet");
    return;
  }
#endif

  // Unknown command
  sendError("unknown command");
}

/**
 * @brief Function that handles unlocking of car
 *
 * Receives unlock message, validates password, waits for start message,
 * then sends unlock flag and feature flags to host.
 *
 * Message format sent to host on success:
 *   OK: <unlock_flag_64_bytes>
 *   OK: 1,<feature1_flag_64_bytes>   (if feature 1 enabled)
 *   OK: 2,<feature2_flag_64_bytes>   (if feature 2 enabled)
 *   OK: 3,<feature3_flag_64_bytes>   (if feature 3 enabled)
 *   OK: done
 */
void unlockCar(void)
{
  //sendOK("Inside unlock car\n");

  MESSAGE_PACKET message;
  uint8_t buffer[64] = {0};
  message.buffer = buffer;

  // Receive unlock message
  receive_board_message_by_type(&message, UNLOCK_MAGIC);

  // Generate and transmit nonce
  message.magic = NONCE_MAGIC;
  message.message_len = NONCE_SIZE;
  uint32_t nonce;
  while( ctr_drbg_generate(&prng_ctx, &nonce) != 0 )
  {
    uint8_t seed[32] = {0};
    getPrngSeed(seed);
    ctr_drbg_reseed(&prng_ctx, seed);
  }
  message.buffer = (uint8_t*)&nonce;
  send_board_message(&message);

  // Compute MAC
  uint8_t computed_mac[16] = {0};
  AES_CMAC_digest(&aes_cmac_ctx, (uint8_t*)&nonce, NONCE_SIZE, computed_mac);

  // Receive response
  uint8_t received_mac[8] = {0};
  message.buffer = received_mac;
  receive_board_message_by_type(&message, RESPONSE_MAGIC);

  if( memcmp(computed_mac, received_mac, 8) != 0 )
  {
    sendAckFailure();
    return;
  }

#ifndef TEST_BUILD
  // In production mode: send unlock flag and feature flags
  uint8_t flag_buffer[FLAG_SIZE] = {0};

  // Send unlock flag
  loadFlag(flag_buffer, UNLOCK);
  uart_write(HOST_UART, flag_buffer, FLAG_SIZE);
  char * newlines = "\n\r";
  uart_write(HOST_UART, (uint8_t*)newlines, 2);
#endif

  // Update state
  carLocked = false;
  unlockCount++;
  setLED(GREEN);

  // Password matches - send success ACK
  sendAckSuccess();

  // Wait for start message with feature data
  message.buffer = buffer;
  receive_board_message_by_type(&message, START_MAGIC);

  FEATURE_DATA *feature_info = (FEATURE_DATA *)buffer;

  // Verify car ID matches (compare exactly 8 bytes)
  if (strcmp(car_id, feature_info->car_id) != 0)
  {
      return;
  }

#ifdef TEST_BUILD
  // Store features
  memcpy(last_feature_info, &feature_info->num_active, NUM_FEATURES+1);
#endif

#ifndef TEST_BUILD
  // Send feature flags
  for (int i = 0; i < feature_info->num_active; i++)
  {
      uint8_t featureNum = feature_info->features[i];
      if (featureNum >= 1 && featureNum <= NUM_FEATURES)
      {
          loadFlag(flag_buffer, (flag_t)(NUM_FEATURES - featureNum));
          uart_write(HOST_UART, flag_buffer, FLAG_SIZE);
          uart_write(HOST_UART, (uint8_t*)newlines, 2);
      }
  }
#endif
}

/**
 * @brief Function to send successful ACK message
 */
void sendAckSuccess(void)
{
  // Create packet for successful ack and send
  MESSAGE_PACKET message;

  uint8_t buffer[1];
  message.buffer = buffer;
  message.magic = ACK_MAGIC;
  buffer[0] = ACK_SUCCESS;
  message.message_len = 1;

  send_board_message(&message);
}

/**
 * @brief Function to send unsuccessful ACK message
 */
void sendAckFailure(void)
{
  // Create packet for unsuccessful ack and send
  MESSAGE_PACKET message;

  uint8_t buffer[1];
  message.buffer = buffer;
  message.magic = ACK_MAGIC;
  buffer[0] = ACK_FAIL;
  message.message_len = 1;

  send_board_message(&message);
}