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

#include "secrets.h"
#include "messages.h"
#include "dataFormats.h"
#include "uart.h"
#include "platform.h"

/*** Macros ***/
#define MAX_CMD_LEN 64

/*** Function definitions ***/
// Core functions - unlockCar and startCar
void unlockCar(void);
void startCar(void);

// Helper functions - sending ack messages
void sendAckSuccess(void);
void sendAckFailure(void);

// Command processing
void processHostCommand(const char *cmd);
void sendOK(const char *value);
void sendError(const char *reason);

// Declare password
const uint8_t pass[] = PASSWORD;
const uint8_t car_id[] = CAR_ID;

// State variables
static bool carLocked = true;
static uint32_t unlockCount = 0;

/**
 * @brief Main function for the car example
 *
 * Initializes the RF module and waits for a successful unlock attempt.
 * If successful prints out the unlock flag.
 */
int main(int argc, char **argv)
{
  initHardware_car(argc, argv);

  // Reset state on startup
  carLocked = true;
  unlockCount = 0;

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
      else if (cmdIndex < MAX_CMD_LEN - 1)
      {
        cmdBuffer[cmdIndex++] = c;
      }
    }

    // Check for board messages (non-blocking)
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

  // Test command: restart (software reset)
  if (strcmp(cmd, "restart") == 0)
  {
    // Note: We send OK before restart; the device will send "OK: started" on boot
    softwareReset();
    // Won't reach here
    return;
  }

  // Test command: reset (factory reset)
  if (strcmp(cmd, "reset") == 0)
  {
    carLocked = true;
    unlockCount = 0;
    // For car, factory reset just resets runtime state
    // A full factory reset would also clear EEPROM, but car has no persistent state
    sendOK(NULL);
    return;
  }
#endif

  // Unknown command
  sendError("unknown command");
}

/**
 * @brief Send OK response to host
 */
void sendOK(const char *value)
{
  if (value)
  {
    char buf[128];
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
  MESSAGE_PACKET message;
  uint8_t buffer[256];
  message.buffer = buffer;

  // Receive unlock message
  receive_board_message_by_type(&message, UNLOCK_MAGIC);

  // Validate password
  if (memcmp(message.buffer, pass, sizeof(pass)) != 0)
  {
    sendError("bad password");
    sendAckFailure();
    return;
  }

  // Password matches - send success ACK
  sendAckSuccess();

  // Wait for start message with feature data
  receive_board_message_by_type(&message, START_MAGIC);

  FEATURE_DATA *feature_info = (FEATURE_DATA *)buffer;

  // Verify car ID matches
  if (memcmp(car_id, feature_info->car_id, sizeof(car_id)) != 0)
  {
    sendError("car id mismatch");
    return;
  }

  // Send unlock flag
  uint8_t flag_buffer[((UNLOCK_SIZE > FEATURE_SIZE) ? UNLOCK_SIZE : FEATURE_SIZE) +1] = {0};
  char msg_buffer[128];

  loadFlag(flag_buffer, UNLOCK);
  sendOK((char*)flag_buffer);
  memset(flag_buffer, 0, sizeof(flag_buffer));

  // Send feature flags
  for (int i = 0; i < feature_info->num_active; i++)
  {
    uint8_t featureNum = feature_info->features[i];
    if (featureNum >= 1 && featureNum <= NUM_FEATURES)
    {
      loadFlag(flag_buffer, (flag_t)featureNum);
      snprintf(msg_buffer, sizeof(msg_buffer), "%d,%.64s", featureNum, flag_buffer);
      sendOK(msg_buffer);
    }
  }

  // Send terminator
  sendOK("done");

  // Update state
  carLocked = false;
  unlockCount++;

  // Change LED color: green
  setLED(GREEN);
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