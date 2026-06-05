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

/*** Macros ***/
#define MAX_CMD_LEN 128

/*** Structure definitions ***/
// Defines a struct for the format of an enable message
typedef struct {
  char car_id[11];
  uint8_t feature;
} ENABLE_PACKET;

/*** Function definitions ***/
// Core functions - all functionality supported by fob
void pairFob(FOB_FLASH_DATA *fob_state_ram, const char *pin);
void enableFeature(FOB_FLASH_DATA *fob_state_ram, const uint8_t *data, size_t len);
void attemptUnlock(FOB_FLASH_DATA *fob_state_ram);
void receivePairData(FOB_FLASH_DATA *fob_state_ram);

/* AES-ECB context used by the CMAC callback; key loaded once in main() */
static struct AES_ctx cmac_ctx;
/* AES-CMAC context storing the AES callback pointer */
static struct AES_CMAC_ctx aes_cmac_ctx;

void aes_cmac_encrypt(uint8_t* data) {
  AES_ECB_encrypt(&cmac_ctx, data);
}

// Helper functions
uint8_t receiveAck(void);
void processHostCommand(FOB_FLASH_DATA *fob_state_ram, const char *cmd);
static void initFobState(FOB_FLASH_DATA *fob_state_ram);

// Declare const variables
const uint8_t my_id = FOB_ID;

static void initFobState(FOB_FLASH_DATA *fob_state_ram)
{
#if PAIRED == 1
  if (FLASH_UNINITIALIZED == fob_state_ram->paired)
  {
    memset(fob_state_ram, 0, sizeof(FOB_FLASH_DATA));
    strcpy(fob_state_ram->pair_info.pin, PAIR_PIN);
    strcpy(fob_state_ram->pair_info.car_id, CAR_ID);
    strcpy(fob_state_ram->feature_info.car_id, CAR_ID);
    fob_state_ram->paired = FLASH_PAIRED;
    fob_state_ram->feature_info.num_active = 0;
    saveFobState(fob_state_ram);
  }
#else
  if (0xFF == fob_state_ram->feature_info.num_active)
  {
    fob_state_ram->feature_info.num_active = 0;
    saveFobState(fob_state_ram);
  }
#endif
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
  const uint8_t aes_key[16] = KEY;
  AES_init_ctx(&cmac_ctx, aes_key);
  /* provide the CMAC library with AES encryption callback function that will perform the actual AES encryption */
  AES_CMAC_init_ctx(&aes_cmac_ctx, &aes_cmac_encrypt);

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
    uint8_t data[32];
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
    sendOK(NULL);
    return;
  }

  // Test command: sendRawBoardMsg <hex>
  if (strncmp(cmd, "sendBoardMsg ", 13) == 0)
  {
    uint8_t raw[MAX_MSG_LEN];
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
  if (strcmp(pin, fob_state_ram->pair_info.pin) != 0)
  {
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
    sprintf(msg, "invalid packet; expected len of 12, got len of %zu", len);
    sendError(msg);
    return;
  }

  ENABLE_PACKET *enable_message = (ENABLE_PACKET *)data;
  enable_message->car_id[10] = '\0';

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

  // Send unlock message with password
  MESSAGE_PACKET message;

  // msg_buf is used first to store the input to AES-CMAC and the MAC result
  // Once the MAC is computed, msg_buf.payload forms the message
  // Layout of buffer before AES_CMAC_digest:
  //          1 byte      1 byte   1 byte   2 bytes   16 bytes
  //     [ UNLOCK_MAGIC | Length | Fob ID | Counter | Padding ]
  // Layout of buffer after AES_CMAC_digest:
  //          1 byte      1 byte   1 byte   2 bytes  16 bytes
  //     [ UNLOCK_MAGIC | Length | Fob ID | Counter | MAC ]
  //                               \------message------/ (first 8 bytes of MAC only)
  UNLOCK_MSG_BUF msg_buf = {0};

  msg_buf.magic = UNLOCK_MAGIC;
  msg_buf.length = sizeof(UNLOCK_PACKET);
  msg_buf.payload.fob_id = my_id;
  msg_buf.payload.counter = ++fob_state_ram->rolling_counter;
  saveFobState(fob_state_ram);
  AES_CMAC_digest(&aes_cmac_ctx, (uint8_t*)&msg_buf, offsetof(UNLOCK_MSG_BUF, payload.mac), msg_buf.payload.mac);
  message.magic = msg_buf.magic;
  message.message_len = msg_buf.length;
  message.buffer = (uint8_t*)&msg_buf.payload;

  send_board_message(&message);

  // Wait for ACK from car (with timeout)
  // TODO: Add timeout to prevent hanging if car doesn't respond
  uint8_t ack_result = receiveAck();

  if (ack_result != ACK_SUCCESS)
  {
    sendError("unlock failed");
    return;
  }

  // ACK received - send start message with feature data
  message.magic = START_MAGIC;
  message.message_len = sizeof(FEATURE_DATA);
  message.buffer = (uint8_t *)&fob_state_ram->feature_info;
  send_board_message(&message);

  // Unlock successful
  sendOK(NULL);
}

void receivePairData(FOB_FLASH_DATA *fob_state_ram)
{
  MESSAGE_PACKET message;
  uint8_t buffer[255];
  message.buffer = buffer;

  receive_board_message_by_type(&message, PAIR_MAGIC);
  
  memcpy((uint8_t*)&fob_state_ram->pair_info, (uint8_t*)buffer, sizeof(PAIR_PACKET));
  fob_state_ram->pair_info.car_id[10] = '\0';
  fob_state_ram->pair_info.pin[6] = '\0';
  fob_state_ram->paired = FLASH_PAIRED;
  strcpy(fob_state_ram->feature_info.car_id, fob_state_ram->pair_info.car_id);
  saveFobState(fob_state_ram);
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
  receive_board_message_by_type(&message, ACK_MAGIC);

  return message.buffer[0];
}