/**
 * @file fobFirmware.c
 * @author Frederich Stine
 * @brief eCTF Fob Example Design Implementation
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

#include "secrets.h"
#include "messages.h"
#include "dataFormats.h"
#include "uart.h"
#include "platform.h"
#include "host_msg_helpers.h"
#include "aes_cmac.h"
#include "aes.h"
#include "memcmp_ct.h"

/*** Macros ***/
#define MAX_CMD_LEN 1040

// sendBoardMsg's own hex-decode scratch buffer (see below): sized to carry a
// full MESSAGE_PACKET regardless of MAX_MSG_LEN, so this TEST_BUILD-only
// command can inject realistic oversized/malicious payloads for security
// testing instead of being artificially capped by the real wire-message size.
#define TEST_SENDBOARDMSG_BUF_LEN 257  // 1 magic + 1 message_len + 255 max payload

/*** Structure definitions ***/
// Defines a struct for the format of an enable message
typedef struct {
  char car_id[11];
  uint8_t feature;
  uint8_t mac[8];
} ENABLE_PACKET;

/*** Static variables ***/
/* AES-ECB context used by the CMAC callback; key loaded once in main() */
static struct AES_ctx unlock_aes_ctx, start_aes_ctx, feature_aes_ctx;
/* AES-CMAC context storing the AES callback pointer */
static struct AES_CMAC_ctx unlock_cmac_ctx, start_cmac_ctx, feature_cmac_ctx;

#ifdef TEST_BUILD
static uint32_t last_pair_memcmp_execution_time;
static uint32_t last_feature_memcmp_execution_time;
static bool custom_start_msg = false;
static uint8_t start_msg[sizeof(START_PACKET)] = {0};
#endif

/*** Function definitions ***/
// Core functions - all functionality supported by fob
void pairFob(FOB_FLASH_DATA *fob_state_ram, const char *pin);
void enableFeature(FOB_FLASH_DATA *fob_state_ram, const uint8_t *data, size_t len);
void attemptUnlock(FOB_FLASH_DATA *fob_state_ram);
void receivePairData(FOB_FLASH_DATA *fob_state_ram);
// Helper functions
uint8_t receiveAck(void);
void processHostCommand(FOB_FLASH_DATA *fob_state_ram, const char *cmd);

static void aes_unlock_cmac(uint8_t* data) {
  AES_ECB_encrypt(&unlock_aes_ctx, data);
}

static void aes_start_cmac(uint8_t* data) {
  AES_ECB_encrypt(&start_aes_ctx, data);
}

static void aes_feature_cmac(uint8_t* data) {
  AES_ECB_encrypt(&feature_aes_ctx, data);
}

static void initUnlockAes(const uint8_t *key)
{
  static uint8_t unlock_key[16];
  memcpy(unlock_key, key, sizeof(unlock_key));
  AES_init_ctx(&unlock_aes_ctx, unlock_key);
  AES_CMAC_init_ctx(&unlock_cmac_ctx, (void*)&aes_unlock_cmac);
}

static void initStartAes(const uint8_t *key)
{
  static uint8_t start_key[16];
  memcpy(start_key, key, sizeof(start_key));
  AES_init_ctx(&start_aes_ctx, start_key);
  AES_CMAC_init_ctx(&start_cmac_ctx, (void*)&aes_start_cmac);
}

static void initFobState(FOB_FLASH_DATA *fob_state_ram)
{
  if (FLASH_UNINITIALIZED == fob_state_ram->paired)
  {
    memset(fob_state_ram, 0, sizeof(FOB_FLASH_DATA));
    hexToBytes(PAIR_PIN, fob_state_ram->pair_info.pin, 3);
    strcpy(fob_state_ram->pair_info.car_id, CAR_ID);
    strcpy(fob_state_ram->feature_info.car_id, CAR_ID);
    const uint8_t unlock_key[16] = UNLOCK_KEY;
    memcpy(fob_state_ram->pair_info.unlock_key, unlock_key, sizeof(unlock_key));
    const uint8_t start_key[16] = START_KEY;
    memcpy(fob_state_ram->pair_info.start_key, start_key, sizeof(start_key));
    fob_state_ram->paired = PAIRED;
    saveFobState(fob_state_ram);
  }
  initUnlockAes(fob_state_ram->pair_info.unlock_key);
  initStartAes(fob_state_ram->pair_info.start_key);
}

/**
 * @brief Main function for the fob example
 *
 * Listens for host commands and button presses. If unpaired, also listens
 * for pairing messages on the board UART.
 */
int main(int argc, char **argv)
{
  initHardware_fob(argc, argv);

  /* expand the key into AES round keys once; reused for every CMAC call */
  const uint8_t feature_key[16] = FEATURE_KEY;
  AES_init_ctx(&feature_aes_ctx, feature_key);
  /* provide the CMAC library with AES encryption callback function that will perform the actual AES encryption */
  AES_CMAC_init_ctx(&feature_cmac_ctx, (void*)&aes_feature_cmac);

  FOB_FLASH_DATA fob_state_ram = {0};
  loadFobState(&fob_state_ram);

  initFobState(&fob_state_ram);

  // Signal ready to host
  uart_write(HOST_UART, (uint8_t *)"OK: started\n", 12);

  // Buffer for host commands
  char cmdBuffer[MAX_CMD_LEN];
  uint16_t cmdIndex = 0;

  // Infinite loop for polling UART and button
  while (true)
  {
    // Non-blocking UART polling for host commands (always active)
    if (uart_avail(HOST_UART))
    {
      uint8_t c = (uint8_t)uart_readb(HOST_UART);

      if ('\n' == c || '\r' == c)
      {
        if (cmdIndex > 0)
        {
          cmdBuffer[cmdIndex] = '\0';
          processHostCommand(&fob_state_ram, cmdBuffer);
          cmdIndex = 0;
        }
      }
      else if ( (cmdIndex < MAX_CMD_LEN - 1) && (isalnum(c) || ' ' == c) )
      {
        cmdBuffer[cmdIndex++] = c;
      }
    }

    if (FLASH_PAIRED == fob_state_ram.paired)
    {
      // Paired fob: check for button press
      if (buttonPressed()) attemptUnlock(&fob_state_ram);
    }
    else
    {
      // Unpaired fob: listen for pairing message on board UART
      if (uart_avail(BOARD_UART)) receivePairData(&fob_state_ram);
    }
  }
}

/**
 * @brief Process a command received from the host
 */
void processHostCommand(FOB_FLASH_DATA *fob_state_ram, const char *cmd)
{
  // Standard command: enable <hex_data>
  if (strncmp(cmd, "enable ", 7) == 0)
  {
    uint8_t data[64];
    int len = hexToBytes(cmd + 7, data, sizeof(data));
    if (len < 0)
    {
      sendError("invalid hex");
      return;
    }
    enableFeature(fob_state_ram, data, len);
    return;
  }

  // Standard command: pair <pin>
  if (strncmp(cmd, "pair ", 5) == 0)
  {
    pairFob(fob_state_ram, cmd + 5);
    return;
  }

#ifdef TEST_BUILD
  // Test command: btnPress (simulate button press, blocks until unlock completes)
  if (strcmp(cmd, "btnPress") == 0)
  {
    attemptUnlock(fob_state_ram);
    return;
  }

  // Test command: isPaired
  if (strcmp(cmd, "isPaired") == 0)
  {
    sendOK((FLASH_PAIRED == fob_state_ram->paired) ? "1" : "0");
    return;
  }

  // Test command: getFlashData
  if (strcmp(cmd, "getFlashData") == 0)
  {
    char hex[sizeof(FOB_FLASH_DATA) * 2 + 1];
    bytesToHex((uint8_t *)fob_state_ram, sizeof(FOB_FLASH_DATA), hex);
    sendOK(hex);
    return;
  }

  // Test command: setFlashData <hex>
  if (strncmp(cmd, "setFlashData ", 13) == 0)
  {
    uint8_t data[sizeof(FOB_FLASH_DATA)];
    int len = hexToBytes(cmd + 13, data, sizeof(data));
    if (len != sizeof(FOB_FLASH_DATA))
    {
      sendError("invalid size");
      return;
    }
    memcpy(fob_state_ram, data, sizeof(FOB_FLASH_DATA));
    saveFobState(fob_state_ram);
    initUnlockAes(fob_state_ram->pair_info.unlock_key);
    initStartAes(fob_state_ram->pair_info.start_key);
    sendOK(NULL);
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
    sendMessageLogAsHex();
    return;
  }

  // Test command: getPairMemcmpTime
  if (strcmp(cmd, "getPairMemcmpTime") == 0)
  {
    char time[16] = {0};
    snprintf(time, 15, "%lu", (unsigned long)last_pair_memcmp_execution_time);
    sendOK(time);
    return;
  }

  // Test command: getFeatureMemcmpTime
  if (strcmp(cmd, "getFeatureMemcmpTime") == 0)
  {
    char time[16] = {0};
    snprintf(time, 15, "%lu", (unsigned long)last_feature_memcmp_execution_time);
    sendOK(time);
    return;
  }

  // Test command: setStartMsg <hex>
  if (strncmp(cmd, "setStartMsg ", 12) == 0)
  {
    int len = hexToBytes(cmd + 12, start_msg, sizeof(start_msg));
    if (len < 2) { sendError("invalid hex"); return; }
    custom_start_msg = true;
    
    sendOK(NULL);
    return;
  }

  // Test command: getStartMsg
  if (strcmp(cmd, "getStartMsg") == 0)
  {
    if( custom_start_msg )
    {
      char hex[sizeof(start_msg) * 2 + 1];
      bytesToHex(start_msg, sizeof(start_msg), hex);
      sendOK(hex);
    }
    else sendError("No start message has been stored (using default values)");
    return;
  }

  // Test command: reset (factory reset)
  if (strcmp(cmd, "reset") == 0)
  {
    memset(fob_state_ram, 0xFF, sizeof(FOB_FLASH_DATA));
    initFobState(fob_state_ram);
    sendOK(NULL);
    return;
  }
#endif

  // Unknown command
  /*
  char msg[64] = {0};
  snprintf(msg, sizeof(msg), "unknown command: %s", cmd);
  sendError(msg);
  */
  sendError("unknown command");
}

/**
 * @brief Function that carries out pairing of the fob (paired fob side only)
 *
 * This is called on a paired fob to initiate pairing with an unpaired fob.
 * Sends: [PAIR_MAGIC] [len] [PAIR_PACKET data] [\n]
 *
 * @param fob_state_ram pointer to the current fob state in ram
 * @param pin the PIN string from the command
 */
void pairFob(FOB_FLASH_DATA *fob_state_ram, const char *pin)
{
  delay_ms(PAIRING_DELAY_MS);

  // Only paired fobs can initiate pairing
  if (fob_state_ram->paired != FLASH_PAIRED)
  {
    sendError("not paired");
    return;
  }

  // Verify PIN length (expect 6 digits)
  if (strlen(pin) != 6)
  {
    sendError("invalid pin length");
    return;
  }

  // Verify PIN matches
  uint8_t hex_pin[3] = {0};
  hexToBytes(pin, hex_pin, 3);

#ifdef TEST_BUILD
  uint32_t start = getHardwareTime();
#endif

  bool pins_match = (memcmp_ct(hex_pin, fob_state_ram->pair_info.pin, 3) == 0);

#ifdef TEST_BUILD
  last_pair_memcmp_execution_time = getHardwareTime() - start;
#endif

  if (!pins_match)
  {
    /*
    char msg[64] = {0};
    char pin_string[7] = {0};
    bytesToHex(fob_state_ram->pair_info.pin, 3, pin_string);
    snprintf(msg, 63, "wrong pin; expected %s, got %s", pin_string, pin);
    sendError(msg);
    */
    sendError("wrong pin");
    return;
  }

  // Pair the new key by sending a PAIR_PACKET structure
  // with required information to unlock door
  MESSAGE_PACKET message;
  message.message_len = sizeof(PAIR_PACKET);
  message.magic = PAIR_MAGIC;
  message.buffer = (uint8_t *)&fob_state_ram->pair_info;
  send_board_message(&message);

  sendOK(NULL);
}

/**
 * @brief Function that handles enabling a new feature on the fob
 *
 * @param fob_state_ram pointer to the current fob state in ram
 * @param data the feature package data
 * @param len length of the data
 */
void enableFeature(FOB_FLASH_DATA *fob_state_ram, const uint8_t *data, size_t len)
{
  if (fob_state_ram->paired != FLASH_PAIRED)
  {
    sendError("not paired");
    return;
  }

  if (len < sizeof(ENABLE_PACKET))
  {
    char msg[64] = {0};
    sprintf(msg, "invalid packet; expected len of 20, got len of %zu", len);
    sendError(msg);
    return;
  }

  ENABLE_PACKET *enable_message = (ENABLE_PACKET *)data;
  enable_message->car_id[10] = '\0';

  // Verify MAC on feature file
  uint8_t computed_mac[16] = {0};
  AES_CMAC_digest(&feature_cmac_ctx, (uint8_t*)enable_message, offsetof(ENABLE_PACKET, mac), computed_mac);

#ifdef TEST_BUILD
  uint32_t start = getHardwareTime();
#endif

  bool macs_match = (memcmp_ct(&computed_mac[8], enable_message->mac, 8) == 0);

#ifdef TEST_BUILD
  last_feature_memcmp_execution_time = getHardwareTime() - start;
#endif

  if (!macs_match)
  {
    sendError("bad MAC");
    return;
  }

  // Verify car ID matches
  if (strcmp(fob_state_ram->pair_info.car_id, enable_message->car_id) != 0)
  {
    sendError("car id mismatch");
    return;
  }

  // Feature list full
  if (fob_state_ram->feature_info.num_active >= NUM_FEATURES)
  {
    sendError("feature list full");
    return;
  }

  // Check feature number is valid
  if (enable_message->feature < 1 || enable_message->feature > NUM_FEATURES)
  {
    sendError("invalid feature");
    return;
  }

  // Search for feature in list (check if already enabled)
  for (int i = 0; i < fob_state_ram->feature_info.num_active; i++)
  {
    if (enable_message->feature == fob_state_ram->feature_info.features[i])
    {
      sendError("already enabled");
      return;
    }
  }

  // Add feature
  fob_state_ram->feature_info.features[fob_state_ram->feature_info.num_active] =
      enable_message->feature;
  fob_state_ram->feature_info.num_active++;

  saveFobState(fob_state_ram);
  sendOK(NULL);
}

/**
 * @brief Attempt to unlock the car
 *
 * Sends unlock message, waits for ACK (with timeout), then sends start 
 * message if successful. Reports result to host.
 *
 * @param fob_state_ram pointer to the current fob state in ram
 */
void attemptUnlock(FOB_FLASH_DATA *fob_state_ram)
{
  if (fob_state_ram->paired != FLASH_PAIRED)
  {
    sendError("not paired");
    return;
  }

  MESSAGE_PACKET message;
  uint8_t buffer[NONCE_SIZE] = {0};
  message.buffer = buffer;

  // Send unlock request
  message.magic = UNLOCK_MAGIC;
  message.message_len = 0;
  send_board_message(&message);

  // Receive nonce message
  receive_board_message_by_type(&message, NONCE_MAGIC, NONCE_SIZE);

  // Craft encrypted response
  uint8_t MAC[16] = {0};
  message.magic = RESPONSE_MAGIC;
  message.message_len = 8;
  message.buffer = MAC;
  AES_CMAC_digest(&unlock_cmac_ctx, buffer, NONCE_SIZE, MAC);
  send_board_message(&message);

  // Wait for ACK from car (with timeout)
  // TODO: Add timeout to prevent hanging if car doesn't respond
  uint8_t ack_result = receiveAck();

  if (ack_result != ACK_SUCCESS)
  {
    sendError("unlock failed");
    return;
  }

  // ACK received - send start message with feature data and MAC

  // msg_buf is used first to store the input to AES-CMAC and the MAC result
  // Once the MAC is computed, msg_buf.payload forms the message
  // Layout of buffer before AES_CMAC_digest:
  //          1 byte     1 byte     15 bytes     16 bytes
  //     [ START_MAGIC | Length | FEATURE_DATA | Padding ]
  // Layout of buffer after AES_CMAC_digest:
  //          1 byte     1 byte     15 bytes     16 bytes
  //     [ START_MAGIC | Length | FEATURE_DATA |   MAC   ]
  //                             \-------message--------/ (first 8 bytes of MAC only)
  START_MSG_BUF msg_buf = {0};

  msg_buf.magic = START_MAGIC;
  msg_buf.length = sizeof(START_PACKET);
  memcpy(&msg_buf.payload.feature_info, (uint8_t *)&fob_state_ram->feature_info, sizeof(FEATURE_DATA));
  AES_CMAC_digest(&start_cmac_ctx, (uint8_t*)&msg_buf, offsetof(START_MSG_BUF, payload.mac), msg_buf.payload.mac);
  
  message.magic = msg_buf.magic;
  message.message_len = msg_buf.length;

#ifdef TEST_BUILD
  message.buffer = custom_start_msg ? start_msg : (uint8_t*)&msg_buf.payload;;
  custom_start_msg = false;
#else
  message.buffer = (uint8_t*)&msg_buf.payload;;
#endif
  send_board_message(&message);

  // Unlock successful
  sendOK(NULL);
}

void receivePairData(FOB_FLASH_DATA *fob_state_ram)
{
  MESSAGE_PACKET message;
  uint8_t buffer[255];
  message.buffer = buffer;

  receive_board_message_by_type(&message, PAIR_MAGIC, 255);
  
  memcpy((uint8_t*)&fob_state_ram->pair_info, (uint8_t*)buffer, sizeof(PAIR_PACKET));
  fob_state_ram->pair_info.car_id[10] = '\0';
  fob_state_ram->paired = FLASH_PAIRED;
  strcpy(fob_state_ram->feature_info.car_id, fob_state_ram->pair_info.car_id);
  saveFobState(fob_state_ram);
  initUnlockAes(fob_state_ram->pair_info.unlock_key);
  initStartAes(fob_state_ram->pair_info.start_key);
}

/**
 * @brief Function that receives an ack and returns whether ack was
 * success/failure
 *
 * @return uint8_t Ack success/failure
 */
uint8_t receiveAck(void)
{
  MESSAGE_PACKET message;
  uint8_t buffer[255];
  message.buffer = buffer;
  receive_board_message_by_type(&message, ACK_MAGIC, 255);

  return message.buffer[0];
}