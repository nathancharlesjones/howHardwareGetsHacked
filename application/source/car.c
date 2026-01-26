/**
 * @file main.c
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

/*** Function definitions ***/
// Core functions - unlockCar and startCar
void unlockCar(void);
void startCar(void);

// Helper functions - sending ack messages
void sendAckSuccess(void);
void sendAckFailure(void);

// Declare password
const uint8_t pass[] = PASSWORD;
const uint8_t car_id[] = CAR_ID;

struct car
{
  asdf
};

/**
 * @brief Main function for the car example
 *
 * Initializes the RF module and waits for a successful unlock attempt.
 * If successful prints out the unlock flag.
 */
void car_init(car_t* c, int argc, char ** argv)
{
  // Things with struct?
  initHardware_car(argc, argv);
}

/**
 * @brief Function that handles unlocking of car
 */
void car_tick(void) {
  // Create a message struct variable for receiving data
  MESSAGE_PACKET message;
  uint8_t buffer[256];
  message.buffer = buffer;

  // Receive packet with some error checking
  receive_board_message_by_type(&message, UNLOCK_MAGIC);

  // Pad payload to a string
  message.buffer[message.message_len] = 0;

  // If the data transfer is the password, unlock
  // ***ERROR HERE?? The password portion of buffer isn't nul-terminated; won't strcmp not work?
  if (!strcmp((char *)(message.buffer), (char *)pass)) {
    uint8_t eeprom_message[UNLOCK_SIZE];
    // Read last 64B of EEPROM
    readVar(eeprom_message, "unlock");

    // Write out full flag if applicable
    uart_write(HOST_UART, eeprom_message, UNLOCK_SIZE);

    sendAckSuccess();

    startCar();
  } else {
    sendAckFailure();
  }
}

/**
 * @brief Function that handles starting of car - feature list
 */
void startCar(void) {
  // Create a message struct variable for receiving data
  MESSAGE_PACKET message;
  uint8_t buffer[256];
  message.buffer = buffer;

  // Receive start message
  receive_board_message_by_type(&message, START_MAGIC);

  FEATURE_DATA *feature_info = (FEATURE_DATA *)buffer;

  // Verify correct car id
  // ***SAME ERROR HERE???
  if (strcmp((char *)car_id, (char *)feature_info->car_id)) {
    return;
  }

  // Print out features for all active features
  for (int i = 0; i < feature_info->num_active; i++) {
    uint8_t eeprom_message[64];
    char* featureNumToStr[] = { "\0", "feature1", "feature2", "feature3" };

    uint8_t featureNum = feature_info->features[i];
    readVar(eeprom_message, featureNumToStr[featureNum]);

    uart_write(HOST_UART, eeprom_message, FEATURE_SIZE);
  }

  // Change LED color: green
  setLED(GREEN);
}

/**
 * @brief Function to send successful ACK message
 */
void sendAckSuccess(void) {
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
void sendAckFailure(void) {
  // Create packet for unsuccessful ack and send
  MESSAGE_PACKET message;

  uint8_t buffer[1];
  message.buffer = buffer;
  message.magic = ACK_MAGIC;
  buffer[0] = ACK_FAIL;
  message.message_len = 1;

  send_board_message(&message);
}
