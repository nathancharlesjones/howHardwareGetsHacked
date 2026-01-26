/**
 * @file gui.h
 * @brief GUI interface for x86 simulation
 * 
 * Provides a simple GUI using microui + SDL2 for:
 * - LED status display
 * - Button input
 * - Serial port status display
 * - Optional board UART reconnection
 */

#ifndef GUI_H
#define GUI_H

#include <stdbool.h>
#include "platform.h"

/**
 * @brief Initialize the GUI subsystem
 * 
 * @param title Window title
 * @return true on success, false on failure
 */
bool gui_init(const char* title);

/**
 * @brief Process one frame of GUI (events + render)
 * 
 * Call this in a loop. Non-blocking.
 * 
 * @return true if GUI should continue, false if window was closed
 */
bool gui_update(void);

/**
 * @brief Shutdown the GUI subsystem
 */
void gui_shutdown(void);

/*
 * Callbacks from GUI to platform (implemented in x86.c)
 */

/** Called when the GUI button is clicked */
void gui_button_callback(void);

/** Called to get current LED color for display */
led_color_t gui_get_led_color(void);

#endif /* GUI_H */
