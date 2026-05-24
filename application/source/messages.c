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

#define MAX_NUM_MSGS 15

typedef struct log_msg
{
  bool tx_msg;
  uint8_t msg[MAX_MSG_LEN];
} logs;

static logs log[MAX_NUM_MSGS+1] = {0};
static uint8_t log_idx = 0;
static uint8_t num_msgs = 0;

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

  // Save sent message to log
  uint8_t idx = log_idx++ & 0xF;
  log[idx].tx_msg = true;
  log[idx].msg[0] = message->magic;
  log[idx].msg[1] = message->message_len;
  memcpy(&log[idx].msg[2], message->buffer, message->message_len);
  num_msgs = (num_msgs == 0xF) ? 0xF : num_msgs + 1;

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

  // Save received message to log
  uint8_t idx = log_idx++ & 0xF;
  log[idx].tx_msg = false; 
  log[idx].msg[0] = message->magic;
  log[idx].msg[1] = message->message_len;
  memcpy(&log[idx].msg[2], message->buffer, message->message_len);
  num_msgs = (num_msgs == 0xF) ? 0xF : num_msgs + 1;
  
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

size_t sizeofMsgLog(void)
{
  return MAX_NUM_MSGS * sizeof(logs);
}

void getMessageLog(uint8_t* buffer)
{
  uint8_t first = (log_idx - num_msgs) & 0xF;
  uint8_t end = log_idx&0xF;
  for(uint8_t send_idx = first, buffer_idx = 0; send_idx != end; send_idx = (send_idx+1)&0xF, buffer_idx++)
  {
    memcpy(buffer + buffer_idx * sizeof(logs), &log[send_idx], sizeof(logs));
  }
}