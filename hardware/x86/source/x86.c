#include <stdbool.h>            // For true/false
#include <pthread.h>            // For pthread_t, pthread_create
#include <stdio.h>              // For getchar
#include <linux/limits.h>       // For PATH_MAX
#include <stdlib.h>             // For exit
#include <libgen.h>             // For dirname
#include <unistd.h>             // For getcwd, access
#include <string.h>             // For strncpy, memcpy
#include <signal.h>             // For signal, SIGTERM, SIGINT

#include "platform.h"
#include "uart.h"
#include "uart_x86.h"
#include "ui.h"

// Defines
#ifndef UNLOCK_FLAG
#   define UNLOCK_FLAG   "default_unlock"
#endif

#ifndef FEATURE1_FLAG
#   define FEATURE1_FLAG "default_feature1"
#endif

#ifndef FEATURE2_FLAG
#   define FEATURE2_FLAG "default_feature2"
#endif

#ifndef FEATURE3_FLAG
#   define FEATURE3_FLAG "default_feature3"
#endif

const char* FLASH_DATA_FILENAME = "flash_data.bin";

// Private variables
static char flash_data_file_path[PATH_MAX] = "";

// Function implementations
static void signal_handler(int sig)
{
    //(void)sig;
    uart_cleanup();
    closeThread();
    exit(0);
}

static void setup_flash_data_file_path(const char* argv0)
{
    char exe_path[PATH_MAX];
    char* dir;
    
    /* Get the directory containing the executable */
    if (realpath(argv0, exe_path) != NULL) {
        dir = dirname(exe_path);
        //snprintf(flash_data_file_path, PATH_MAX, "%s/%s", dir, FLASH_DATA_FILENAME);
        snprintf(flash_data_file_path, PATH_MAX-1, "%.*s/%s", (int)(sizeof(flash_data_file_path)
             - 1 - strlen(FLASH_DATA_FILENAME) - 1), dir, FLASH_DATA_FILENAME);
    } else {
        /* Fallback to current directory */
        if (getcwd(exe_path, PATH_MAX) != NULL) {
            snprintf(flash_data_file_path, PATH_MAX-1, "%.*s/%s", (int)(sizeof(flash_data_file_path)
                - 1 - strlen(FLASH_DATA_FILENAME) - 1), exe_path, FLASH_DATA_FILENAME);
        } else {
            /* Last resort */
            strncpy(flash_data_file_path, FLASH_DATA_FILENAME, PATH_MAX-1);
        }
    }
}

static void initHardware(int argc, char ** argv)
{
    /* Set up state file path based on executable location */
    if (argc > 0 && argv[0] != NULL) {
        setup_flash_data_file_path(argv[0]);
    } else {
        setup_flash_data_file_path("./");
    }
    
    /* Set up signal handlers for clean shutdown */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    /* Initialize UARTs */
    uart_init(HOST_UART, argc, argv);
    uart_init(BOARD_UART, argc, argv);

    initThread(argc, argv);
}

void initHardware_car(int argc, char ** argv)
{
    initHardware(argc, argv);
    setLED(RED);
}

static void create_default_fob_state(void)
{
    FLASH_DATA default_state;
    memset(&default_state, 0xFF, sizeof(FLASH_DATA));
    
    saveFobState(&default_state);
}

void initHardware_fob(int argc, char ** argv)
{
    initHardware(argc, argv);

#ifndef TEST_BUILD
    /* Create default fob state file if it doesn't exist */
    if (access(flash_data_file_path, F_OK) != 0)
#endif
    {
        create_default_fob_state();
    }

    setLED(WHITE); 
}

void loadFlag(uint8_t* dest, flag_t flag)
{
    static const char flags[][64] = {
        [UNLOCK] = UNLOCK_FLAG,
        [FEATURE1] = FEATURE1_FLAG,
        [FEATURE2] = FEATURE2_FLAG,
        [FEATURE3] = FEATURE3_FLAG
    };
    size_t size = (UNLOCK == flag) ? UNLOCK_SIZE : FEATURE_SIZE;
    memcpy(dest, flags[flag], size);
}

void loadFobState(FLASH_DATA* data)
{
    FILE* fp = fopen(flash_data_file_path, "rb");
    if (!fp) {
        //return false;
        return;
    }
    
    size_t read = fread(data, 1, sizeof(FLASH_DATA), fp);
    fclose(fp);
    
    if(read != sizeof(FLASH_DATA)) exit(EXIT_FAILURE);
}

bool saveFobState(const FLASH_DATA* data)
{
    FILE* fp = fopen(flash_data_file_path, "wb");
    if (!fp) {
        return false;
    }
    
    size_t written = fwrite(data, 1, sizeof(FLASH_DATA), fp);
    fclose(fp);

    return (sizeof(FLASH_DATA) == written);
}

void __attribute__((weak)) initThread(int argc, char ** argv)
{
    // Empty
}

void  __attribute__((weak)) closeThread(void)
{
    // Empty
}

void  __attribute__((weak)) setLED(led_color_t color)
{
    // Empty
}

bool  __attribute__((weak)) buttonPressed(void)
{
    // Empty
    return false;
}