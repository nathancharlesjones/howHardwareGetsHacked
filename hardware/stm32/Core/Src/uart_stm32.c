/**
 * @file uart.c
 * @author Kyle Scaplen
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
#include <string.h>

#include "main.h"
#include "uart.h"
#include "uart_stm32.h"

/**
 * @brief Initialize the UART interfaces.
 *
 * UART 0 is used to communicate with the host computer.
 */
void uart_init(void) {}

/**
 * @brief Check if there are characters available on a UART interface.
 *
 * @param uart is the base address of the UART port.
 * @return true if there is data available.
 * @return false if there is no data available.
 */
bool uart_avail(hw_uart_t uart) { return (__HAL_UART_GET_FLAG(uart_base(uart), UART_FLAG_RXNE) != RESET); }

/**
 * @brief Read a byte from a UART interface.
 *
 * @param uart is the base address of the UART port to read from.
 * @return the character read from the interface.
 */
int32_t uart_readb(hw_uart_t uart)
{
  int32_t c;
  HAL_UART_Receive(uart_base(uart), (uint8_t*)(&c), 1, HAL_MAX_DELAY);
  //return UARTCharGet(uart_base(uart));
  return c;
}

/**
 * @brief Read a sequence of bytes from a UART interface.
 *
 * @param uart is the base address of the UART port to read from.
 * @param buf is a pointer to the destination for the received data.
 * @param n is the number of bytes to read.
 * @return the number of bytes read from the UART interface.
 */
uint32_t uart_read(hw_uart_t uart, uint8_t *buf, uint32_t n) {
  /*
  uint32_t read;
  UART_HandleTypeDef* base = uart_base(uart);

  for (read = 0; read < n; read++) {
    //buf[read] = (uint8_t)uart_readb(base);
  }
  */
  HAL_UART_Receive(uart_base(uart), buf, n, HAL_MAX_DELAY);

  return n;
}

/**
 * @brief Read a line (terminated with '\n') from a UART interface.
 *
 * @param uart is the base address of the UART port to read from.
 * @param buf is a pointer to the destination for the received data.
 * @return the number of bytes read from the UART interface.
 */
uint32_t uart_readline(hw_uart_t uart, uint8_t *buf) {
  uint32_t read = 0;
  uint8_t c;
  UART_HandleTypeDef* base = uart_base(uart);

  do {
    //c = (uint8_t)uart_readb(base);
    HAL_UART_Receive(base, &c, 1, HAL_MAX_DELAY);

    if ((c != '\r') && (c != '\n') && (c != 0xD)) {
      buf[read] = c;
      read++;
    }

  } while ((c != '\n') && (c != 0xD));

  buf[read] = '\0';

  return read;
}

/**
 * @brief Write a byte to a UART interface.
 *
 * @param uart is the base address of the UART port to write to.
 * @param data is the byte value to write.
 */
void uart_writeb(hw_uart_t uart, uint8_t data) { HAL_UART_Transmit(uart_base(uart), &data, 1, HAL_MAX_DELAY); }

/**
 * @brief Write a sequence of bytes to a UART interface.
 *
 * @param uart is the base address of the UART port to write to.
 * @param buf is a pointer to the data to send.
 * @param len is the number of bytes to send.
 * @return the number of bytes written.
 */
uint32_t uart_write(hw_uart_t uart, uint8_t *buf, uint32_t len) {
  /*
  uint32_t i;
  UART_HandleTypeDef* base = uart_base(uart);

  for (i = 0; i < len; i++) {
    uart_writeb(base, buf[i]);
  }
  */
  HAL_UART_Transmit(uart_base(uart), buf, len, HAL_MAX_DELAY);

  return len;
}
