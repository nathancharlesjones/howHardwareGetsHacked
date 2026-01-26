/**
 * @file x86.c
 * @brief x86 simulation platform implementation
 * 
 * Implements platform.h functions for x86 Linux simulation using:
 * - Binary file for persistent storage (mimics Flash/EEPROM)
 * - microui + SDL2 for GUI (LED display, button input)
 * - pthreads for non-blocking GUI updates
 * - Signal handlers for clean shutdown
 * 
 * Compile-time defines expected:
 *   For car: -DCAR_ID=... -DPASSWORD=... -DUNLOCK_FLAG=... 
 *            -DFEATURE1_FLAG=... -DFEATURE2_FLAG=... -DFEATURE3_FLAG=...
 *   For fob: -DCAR_ID=... -DPASSWORD=... -DPAIR_PIN=... -DPAIRED=0 or -DPAIRED=1
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <signal.h>
#include <pthread.h>
#include <unistd.h>
#include <libgen.h>
#include <linux/limits.h>

#include "platform.h"
#include "uart.h"
#include "dataFormats.h"
#include "gui.h"

/*******************************************************************************
 * Compile-time secrets
 ******************************************************************************/
#ifndef UNLOCK_FLAG
#define UNLOCK_FLAG   "default_unlock"
#endif
#ifndef FEATURE1_FLAG
#define FEATURE1_FLAG "default_feature1"
#endif
#ifndef FEATURE2_FLAG
#define FEATURE2_FLAG "default_feature2"
#endif
#ifndef FEATURE3_FLAG
#define FEATURE3_FLAG "default_feature3"
#endif

/*******************************************************************************
 * Constants for car (read-only secrets)
 ******************************************************************************/
static const uint8_t car_id[] = CAR_ID;
static const uint8_t password[] = PASSWORD;
static const uint8_t unlock_flag[UNLOCK_SIZE] = UNLOCK_FLAG;
static const uint8_t feature1_flag[FEATURE_SIZE] = FEATURE1_FLAG;
static const uint8_t feature2_flag[FEATURE_SIZE] = FEATURE2_FLAG;
static const uint8_t feature3_flag[FEATURE_SIZE] = FEATURE3_FLAG;
static const uint8_t pair_pin[] = PAIR_PIN;

/*******************************************************************************
 * File-local variables
 ******************************************************************************/
#define STATE_FILENAME "state.bin"

static char state_file_path[PATH_MAX] = "";
static led_color_t current_led_color = OFF;
static volatile bool button_pressed_flag = false;
static volatile bool button_consumed = true;
static pthread_t gui_thread;
static volatile bool gui_running = false;
static pthread_mutex_t button_mutex = PTHREAD_MUTEX_INITIALIZER;

/*******************************************************************************
 * Forward declarations
 ******************************************************************************/
static void cleanup_handler(void);
static void signal_handler(int sig);
static void* gui_thread_func(void* arg);
static void setup_state_file_path(const char* argv0);

/*******************************************************************************
 * Signal and cleanup handling
 ******************************************************************************/
static void cleanup_handler(void)
{
    if (gui_running) {
        gui_running = false;
        pthread_join(gui_thread, NULL);
    }
    uart_cleanup();
    gui_shutdown();
}

static void signal_handler(int sig)
{
    (void)sig;
    cleanup_handler();
    exit(0);
}

/*******************************************************************************
 * State file path setup
 ******************************************************************************/
static void setup_state_file_path(const char* argv0)
{
    char exe_path[PATH_MAX];
    char* dir;
    
    /* Get the directory containing the executable */
    if (realpath(argv0, exe_path) != NULL) {
        dir = dirname(exe_path);
        snprintf(state_file_path, PATH_MAX, "%s/%s", dir, STATE_FILENAME);
    } else {
        /* Fallback to current directory */
        if (getcwd(exe_path, PATH_MAX) != NULL) {
            snprintf(state_file_path, PATH_MAX, "%s/%s", exe_path, STATE_FILENAME);
        } else {
            /* Last resort */
            strncpy(state_file_path, STATE_FILENAME, PATH_MAX);
        }
    }
}

/*******************************************************************************
 * GUI thread
 ******************************************************************************/

/* Callback from GUI when button is clicked */
void gui_button_callback(void)
{
    pthread_mutex_lock(&button_mutex);
    button_pressed_flag = true;
    button_consumed = false;
    pthread_mutex_unlock(&button_mutex);
}

/* Callback from GUI to get current LED color */
led_color_t gui_get_led_color(void)
{
    return current_led_color;
}

static void* gui_thread_func(void* arg)
{
    const char* title = (const char*)arg;
    
    if (!gui_init(title)) {
        fprintf(stderr, "Failed to initialize GUI\n");
        return NULL;
    }
    
    while (gui_running) {
        if (!gui_update()) {
            /* Window was closed */
            gui_running = false;
            /* Trigger cleanup in main thread */
            raise(SIGTERM);
            break;
        }
    }
    
    return NULL;
}

/*******************************************************************************
 * Binary State File Handling (for fob)
 ******************************************************************************/

static bool load_fob_state(FLASH_DATA* data)
{
    FILE* fp = fopen(state_file_path, "rb");
    if (!fp) {
        return false;
    }
    
    size_t read = fread(data, 1, sizeof(FLASH_DATA), fp);
    fclose(fp);
    
    return (read == sizeof(FLASH_DATA));
}

static bool save_fob_state(const FLASH_DATA* data)
{
    FILE* fp = fopen(state_file_path, "wb");
    if (!fp) {
        return false;
    }
    
    size_t written = fwrite(data, 1, sizeof(FLASH_DATA), fp);
    fclose(fp);
    
    return (written == sizeof(FLASH_DATA));
}

static void create_default_fob_state(void)
{
    FLASH_DATA default_state = {
        .paired = FLASH_UNPAIRED,
        .pair_info = {
            .car_id = {0},
            .password = {0},
            .pin = {0}
        },
        .feature_info = {
            .car_id = {0},
            .num_active = 0xFF,
            .features = {0}
        }
    };
    
    save_fob_state(&default_state);
}

/*******************************************************************************
 * Platform API Implementation
 ******************************************************************************/

/* Declared in uart_x86.c */
extern void uart_set_args(int argc, char** argv);

static void initHardware_common(int argc, char** argv, const char* window_title)
{
    /* Set up state file path based on executable location */
    if (argc > 0 && argv[0] != NULL) {
        setup_state_file_path(argv[0]);
    } else {
        setup_state_file_path("./");
    }
    
    /* Set up signal handlers for clean shutdown */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    atexit(cleanup_handler);
    
    /* Initialize UARTs - pass args first, then init each */
    uart_set_args(argc, argv);
    uart_init(HOST_UART);
    uart_init(BOARD_UART);
    
    /* Start GUI thread */
    gui_running = true;
    if (pthread_create(&gui_thread, NULL, gui_thread_func, (void*)window_title) != 0) {
        fprintf(stderr, "Failed to create GUI thread\n");
        gui_running = false;
    }
}

void initHardware_car(int argc, char** argv)
{
    initHardware_common(argc, argv, "Car Simulation");
    setLED(RED);
}

void initHardware_fob(int argc, char** argv)
{
    initHardware_common(argc, argv, "Fob Simulation");
    
    /* Create default fob state file if it doesn't exist */
    if (access(state_file_path, F_OK) != 0) {
        create_default_fob_state();
    }
    
    setLED(WHITE);
}

void readVar(uint8_t* dest, char* var)
{
    /*
     * Car uses this to read compile-time secrets.
     * Fob uses this only for "fob_state".
     */
    if (!strcmp(var, "unlock")) {
        memcpy(dest, unlock_flag, UNLOCK_SIZE);
    }
    else if (!strcmp(var, "feature1")) {
        memcpy(dest, feature1_flag, FEATURE_SIZE);
    }
    else if (!strcmp(var, "feature2")) {
        memcpy(dest, feature2_flag, FEATURE_SIZE);
    }
    else if (!strcmp(var, "feature3")) {
        memcpy(dest, feature3_flag, FEATURE_SIZE);
    }
    else if (!strcmp(var, "fob_state")) {
        FLASH_DATA state = {0};
        if (load_fob_state(&state)) {
            memcpy(dest, &state, sizeof(FLASH_DATA));
        }
    }
}

bool saveFobState(const FLASH_DATA* flash_data)
{
    return save_fob_state(flash_data);
}

void setLED(led_color_t color)
{
    current_led_color = color;
}

bool buttonPressed(void)
{
    bool pressed = false;
    
    pthread_mutex_lock(&button_mutex);
    if (button_pressed_flag && !button_consumed) {
        pressed = true;
        button_consumed = true;
        button_pressed_flag = false;
    }
    pthread_mutex_unlock(&button_mutex);
    
    return pressed;
}
