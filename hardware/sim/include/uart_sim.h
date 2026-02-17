/**
 * @file uart_sim.h
 * @brief Simulation-specific UART extensions
 * 
 * These functions are only available on the simulation build
 * and are not part of the standard uart.h interface.
 */

#ifndef UART_SIM_H
#define UART_SIM_H

#include <stdbool.h>

/**
 * @brief Clean up and close all open serial ports
 */
void uart_cleanup(void);

/**
 * @brief Reconnect the board UART to a different serial port
 * 
 * Closes the current board UART connection (if any) and opens
 * a new connection to the specified path.
 * 
 * @param new_path Path to the new serial port
 * @return true on success, false on failure
 */
bool uart_reconnect_board(const char* new_path);

/**
 * @brief Get the current board UART path
 * @return Pointer to the path string (empty if not connected)
 */
const char* uart_get_board_path(void);

/**
 * @brief Get the current host UART path
 * @return Pointer to the path string (empty if not connected)
 */
const char* uart_get_host_path(void);

#endif /* UART_SIM_H */
