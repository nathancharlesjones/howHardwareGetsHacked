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

#include "secrets.h"
#include "messages.h"
#include "dataFormats.h"
#include "uart.h"
#include "platform.h"

/*** Macros ***/
#define MAX_CMD_LEN 256

/*** Structure definitions ***/
// Defines a struct for the format of an enable message
typedef struct {
  char car_id[11];
  uint8_t feature;
} ENABLE_PACKET;

/*** Function definitions ***/
// Core functions - all functionality supported by fob
void pairFob(FLASH_DATA *fob_state_ram, const char *pin);
void unlockCar(FLASH_DATA *fob_state_ram);
void enableFeature(FLASH_DATA *fob_state_ram, const uint8_t *data, size_t len);
void startCar(FLASH_DATA *fob_state_ram);
void attemptUnlock(FLASH_DATA *fob_state_ram);
void receivePairData(FLASH_DATA *fob_state_ram);

// Helper functions
uint8_t receiveAck(void);
void processHostCommand(FLASH_DATA *fob_state_ram, const char *cmd);
void sendOK(const char *value);
void sendError(const char *reason);
void bytesToHex(const uint8_t *bytes, size_t len, char *hex);
int hexToBytes(const char *hex, uint8_t *bytes, size_t maxLen);

/**
 * @brief Main function for the fob example
 *
 * Listens for host commands and button presses. If unpaired, also listens
 * for pairing messages on the board UART.
 */
int main(int argc, char **argv)
{
  initHardware_fob(argc, argv);

  FLASH_DATA fob_state_ram = {0};
  loadFobState(&fob_state_ram);

// If paired fob, initialize the system information on first boot
#if PAIRED == 1
  if (FLASH_UNPAIRED == fob_state_ram.paired)
  {
    memset(&fob_state_ram, 0, sizeof(FLASH_DATA));
    strcpy(fob_state_ram.pair_info.password, PASSWORD);
    strcpy(fob_state_ram.pair_info.pin, PAIR_PIN);
    strcpy(fob_state_ram.pair_info.car_id, CAR_ID);
    strcpy(fob_state_ram.feature_info.car_id, CAR_ID);
    fob_state_ram.paired = FLASH_PAIRED;
    fob_state_ram.feature_info.num_active = 0;

    saveFobState(&fob_state_ram);
  }
#else
  // This will run on first boot to initialize features
  if (0xFF == fob_state_ram.feature_info.num_active)
  {
    fob_state_ram.feature_info.num_active = 0;
    saveFobState(&fob_state_ram);
  }  
#endif

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
      else if (cmdIndex < MAX_CMD_LEN - 1)
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
void processHostCommand(FLASH_DATA *fob_state_ram, const char *cmd)
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
    char hex[sizeof(FLASH_DATA) * 2 + 1];
    bytesToHex((uint8_t *)fob_state_ram, sizeof(FLASH_DATA), hex);
    sendOK(hex);
    return;
  }

  // Test command: setFlashData <hex>
  if (strncmp(cmd, "setFlashData ", 13) == 0)
  {
    uint8_t data[sizeof(FLASH_DATA)];
    int len = hexToBytes(cmd + 13, data, sizeof(data));
    if (len != sizeof(FLASH_DATA))
    {
      sendError("invalid size");
      return;
    }
    memcpy(fob_state_ram, data, sizeof(FLASH_DATA));
    saveFobState(fob_state_ram);
    sendOK(NULL);
    return;
  }

  // Test command: reload (reload data from flash)
  if (strcmp(cmd, "reload") == 0)
  {
    loadFobState(fob_state_ram);
    sendOK(NULL);
    return;
  }

  // Test command: reset (factory reset)
  if (strcmp(cmd, "reset") == 0)
  {
    // Should this unpair the fob??
    memset(fob_state_ram, 0, sizeof(FLASH_DATA));
    saveFobState(fob_state_ram);
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
 * @brief Send OK response to host
 */
void sendOK(const char *value)
{
  if (value)
  {
    char buf[512];
    snprintf(buf, sizeof(buf), "OK: %s\n", value);
    uart_write(HOST_UART, (uint8_t *)buf, strlen(buf));
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

/**
 * @brief Function that carries out pairing of the fob (paired fob side only)
 *
 * This is called on a paired fob to initiate pairing with an unpaired fob.
 * Sends: [PAIR_MAGIC] [len] [PAIR_PACKET data] [\n]
 *
 * @param fob_state_ram pointer to the current fob state in ram
 * @param pin the PIN string from the command
 */
void pairFob(FLASH_DATA *fob_state_ram, const char *pin)
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
void enableFeature(FLASH_DATA *fob_state_ram, const uint8_t *data, size_t len)
{
  if (fob_state_ram->paired != FLASH_PAIRED)
  {
    sendError("not paired");
    return;
  }

  if (len < sizeof(ENABLE_PACKET))
  {
    char msg[64] = {0};
    sprintf(msg, "invalid packet; expected len of 12, got len of %ld", len);
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
void attemptUnlock(FLASH_DATA *fob_state_ram)
{
  if (fob_state_ram->paired != FLASH_PAIRED)
  {
    sendError("not paired");
    return;
  }

  // Send unlock message with password
  MESSAGE_PACKET message;
  message.message_len = strlen(fob_state_ram->pair_info.password) + 1;
  message.magic = UNLOCK_MAGIC;
  message.buffer = (uint8_t *)&fob_state_ram->pair_info.password;
  send_board_message(&message);

  // Wait for ACK from car (with timeout)
  // TODO: Add timeout to prevent hanging if car doesn't respond
  uint8_t ack_result = receiveAck();

  if (ack_result != ACK_SUCCESS)
  {
    //char msg[64] = {0};
    //snprintf(msg, 63, "unlock failed; sent %d bytes for pw %8s",message.message_len, (char*)fob_state_ram->pair_info.password);
    //sendError(msg);
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

void receivePairData(FLASH_DATA *fob_state_ram)
{
  static enum {
      PAIR_STATE_WAIT_MAGIC,
      PAIR_STATE_WAIT_LEN,
      PAIR_STATE_WAIT_DATA
  } pairState = PAIR_STATE_WAIT_MAGIC;
  static uint8_t pairBuffer[sizeof(PAIR_PACKET)];
  static uint8_t pairLen = 0;
  static uint8_t pairExpectedLen = 0;

  uint8_t c = (uint8_t)uart_readb(BOARD_UART);

  switch (pairState)
  {
    case PAIR_STATE_WAIT_MAGIC:
        if (PAIR_MAGIC == c)
        {
            pairState = PAIR_STATE_WAIT_LEN;
        }
        // Ignore non-magic bytes
        break;

    case PAIR_STATE_WAIT_LEN:
        pairExpectedLen = c;
        pairLen = 0;
        
        // Validate length
        if (sizeof(PAIR_PACKET) == pairExpectedLen)
        {
            pairState = PAIR_STATE_WAIT_DATA;
        }
        else
        {
            // Invalid length - reset state machine
            pairState = PAIR_STATE_WAIT_MAGIC;
        }
        break;

    case PAIR_STATE_WAIT_DATA:
        pairBuffer[pairLen++] = c;
        
        if (pairLen >= pairExpectedLen)
        {
            // Got complete pairing packet - apply it
            memcpy((uint8_t*)&fob_state_ram->pair_info, (uint8_t*)pairBuffer, sizeof(PAIR_PACKET));
            fob_state_ram->pair_info.car_id[10] = '\0';
            fob_state_ram->pair_info.password[7] = '\0';
            fob_state_ram->pair_info.pin[6] = '\0';
            fob_state_ram->paired = FLASH_PAIRED;
            strcpy(fob_state_ram->feature_info.car_id, fob_state_ram->pair_info.car_id);
            saveFobState(fob_state_ram);
            
            // No async message - test will query isPaired
            
            // Reset state machine (though we're now paired, so this branch won't run)
            pairState = PAIR_STATE_WAIT_MAGIC;
        }
        else if (pairLen >= sizeof(pairBuffer))
        {
            // Buffer overflow - reset state machine
            pairState = PAIR_STATE_WAIT_MAGIC;
        }
        break;
  }
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