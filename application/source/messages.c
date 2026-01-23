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

#include "messages.h"
#include "uart.h"

/**
 * @brief Send a message between boards
 *
 * @param message pointer to message to send
 * @return uint32_t the number of bytes sent
 */
uint32_t send_board_message(MESSAGE_PACKET *message)
{
  uart_writeb(BOARD_UART, message->magic);
  uart_writeb(BOARD_UART, message->message_len);
  uart_write(BOARD_UART, message->buffer, message->message_len);
  return message->message_len;
}

/**
 * @brief Receive a message between boards
 *
 * @param message pointer to message where data will be received
 * @return uint32_t the number of bytes received - 0 for error
 */
uint32_t receive_board_message(MESSAGE_PACKET *message)
{
  message->magic = (uint8_t)uart_readb(BOARD_UART);

  if (message->magic == 0) {
    return 0;
  }

  message->message_len = (uint8_t)uart_readb(BOARD_UART);
  uart_read(BOARD_UART, message->buffer, message->message_len);
  
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
