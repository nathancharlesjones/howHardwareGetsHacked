/**
 * @file board_link.h
 * @author Frederich Stine
 * @brief Firmware UART interface implementation.
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

#include "main.h"
#include "board_link.h"
#include "uart_stm32.h"

/**
 * @brief Set the up board link object
 *
 * UART 1 is used to communicate between boards
 */
void setup_board_link(void) {}

/**
 * @brief Send a message between boards
 *
 * @param message pointer to message to send
 * @return uint32_t the number of bytes sent
 */
uint32_t send_board_message(MESSAGE_PACKET *message) {
  UART_HandleTypeDef* base = uart_base(BOARD_UART);
  HAL_UART_Transmit(base, (uint8_t*)message, (message->message_len)+2, HAL_MAX_DELAY);
  /*
  UARTCharPut(base, message->magic);
  UARTCharPut(base, message->message_len);

  for (int i = 0; i < message->message_len; i++) {
    UARTCharPut(base, message->buffer[i]);
  }
  */

  return message->message_len;
}

/**
 * @brief Receive a message between boards
 *
 * @param message pointer to message where data will be received
 * @return uint32_t the number of bytes received - 0 for error
 */
uint32_t receive_board_message(MESSAGE_PACKET *message) {
  UART_HandleTypeDef* base = uart_base(BOARD_UART);
  //message->magic = (uint8_t)UARTCharGet(base);
  HAL_UART_Receive(base, &(message->magic), 1, HAL_MAX_DELAY);

  if (message->magic == 0) {
    return 0;
  }

  //message->message_len = (uint8_t)UARTCharGet(base);
  HAL_UART_Receive(base, &(message->message_len), 1, HAL_MAX_DELAY);

  /*
  for (int i = 0; i < message->message_len; i++) {
    message->buffer[i] = (uint8_t)UARTCharGet(base);
  }
  */
  HAL_UART_Receive(base, message->buffer, message->message_len, HAL_MAX_DELAY);

  return message->message_len;
}

/**
 * @brief Function that retreives messages until the specified message is found
 *
 * @param message pointer to message where data will be received
 * @param type the type of message to receive
 * @return uint32_t the number of bytes received
 */
uint32_t receive_board_message_by_type(MESSAGE_PACKET *message, uint8_t type) {
  do {
    receive_board_message(message);
  } while (message->magic != type);

  return message->message_len;
}
