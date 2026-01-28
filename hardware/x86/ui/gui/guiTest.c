/**
 * @file guiTest.c
 * @brief Simple test program for the microui + SDL2 GUI
 * 
 * Compile with (from the x86 directory):
 *   gcc -o guiTest guiTest.c gui.c \
 *       ../../libraries/microui/src/microui.c \
 *       -I../../libraries/microui/src \
 *       $(pkg-config --cflags --libs sdl2) -lpthread
 * 
 * Or without pkg-config:
 *   gcc -o guiTest guiTest.c gui.c \
 *       ../../libraries/microui/src/microui.c \
 *       -I../../libraries/microui/src \
 *       -lSDL2 -lpthread
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <unistd.h>

/*******************************************************************************
 * Stub definitions for testing without full platform
 ******************************************************************************/

/* LED color enum (normally from platform.h) */
typedef enum { OFF, RED, GREEN, WHITE } led_color_t;

/* Stub UART functions that gui.c calls */
static char stub_host_path[256] = "/tmp/host_uart";
static char stub_board_path[256] = "/tmp/board_uart";

const char* uart_get_host_path(void) { return stub_host_path; }
const char* uart_get_board_path(void) { return stub_board_path; }
bool uart_reconnect_board(const char* path) { 
    printf("[UART] Reconnecting board UART to: %s\n", path);
    snprintf(stub_board_path, sizeof(stub_board_path), "%s", path);
    return true; 
}

/*******************************************************************************
 * Test state
 ******************************************************************************/
static led_color_t current_led = OFF;
static int button_press_count = 0;

/*******************************************************************************
 * Callbacks that gui.c expects (defined in gui.h)
 ******************************************************************************/
void gui_button_callback(void)
{
    button_press_count++;
    printf("[Button] Pressed! (count: %d)\n", button_press_count);
    
    /* Cycle LED color */
    current_led = (current_led + 1) % 4;
    const char* names[] = {"OFF", "RED", "GREEN", "WHITE"};
    printf("[LED] Changed to: %s\n", names[current_led]);
}

led_color_t gui_get_led_color(void)
{
    return current_led;
}

/*******************************************************************************
 * GUI function declarations (from gui.h)
 ******************************************************************************/
bool gui_init(const char* title);
bool gui_update(void);
void gui_shutdown(void);

/*******************************************************************************
 * Main
 ******************************************************************************/
int main(int argc, char* argv[])
{
    (void)argc;
    (void)argv;
    
    printf("========================================\n");
    printf("  microui + SDL2 GUI Test Program\n");
    printf("========================================\n\n");
    printf("Instructions:\n");
    printf("  - Click 'PAIR / UNLOCK BUTTON' to cycle LED colors\n");
    printf("  - Enter a path and click 'Connect' to test UART reconnect\n");
    printf("  - Close the window to exit\n\n");
    
    if (!gui_init("GUI Test - microui + SDL2")) {
        fprintf(stderr, "ERROR: Failed to initialize GUI\n");
        fprintf(stderr, "Make sure SDL2 is installed: sudo apt-get install libsdl2-dev\n");
        return 1;
    }
    
    printf("[Init] GUI initialized successfully!\n\n");
    
    /* Main loop */
    while (gui_update()) {
        /* gui_update handles everything - events, rendering, etc. */
        /* This loop runs at ~60 FPS due to SDL_Delay in gui_update */
    }
    
    printf("\n[Exit] Window closed, shutting down...\n");
    printf("Total button presses: %d\n", button_press_count);
    
    gui_shutdown();
    
    return 0;
}
