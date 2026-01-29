#include <stdbool.h>            // For true/false
#include <pthread.h>            // For pthread_t, pthread_create
#include <stdio.h>              // For getchar
#include <linux/limits.h>       // For PATH_MAX
#include <stdlib.h>             // For exit
#include <libgen.h>             // For dirname
#include <unistd.h>             // For getcwd, access, execv
#include <string.h>             // For strncpy, memcpy
#include <signal.h>             // For signal, SIGTERM, SIGINT

#include "platform.h"
#include "uart.h"
#include "uart_x86.h"

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
}

void initHardware_car(int argc, char ** argv)
{
    initHardware(argc, argv);
    setLED(RED);
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
    
    saveFobState(&default_state);
}

void initHardware_fob(int argc, char ** argv)
{
    initHardware(argc, argv);
    
    /* Create default fob state file if it doesn't exist */
    if (access(flash_data_file_path, F_OK) != 0) {
        create_default_fob_state();
    }

    FLASH_DATA data;
    loadFobState(&data);
    setLED(WHITE); 
}

void loadFlag(uint8_t* dest, flag_t flag)
{
    static const char* flags[] = {
        [UNLOCK] = UNLOCK_FLAG,
        [FEATURE1] = FEATURE1_FLAG,
        [FEATURE2] = FEATURE2_FLAG,
        [FEATURE3] = FEATURE3_FLAG
    };
    size_t size = (flag == UNLOCK) ? UNLOCK_SIZE : FEATURE_SIZE;
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
    
    return (written == sizeof(FLASH_DATA));
}

void setLED(led_color_t color)
{
}

bool buttonPressed(void)
{
    return false;
}

// Store argv[0] for re-exec
static char *g_exe_path = NULL;
static char **g_argv = NULL;

// Call this from initHardware to save the executable path
void platform_save_argv(int argc, char **argv)
{
    g_exe_path = argv[0];
    g_argv = argv;
}

void softwareReset(void)
{
    // Re-exec ourselves with same arguments
    // This effectively restarts the process
    if (g_exe_path && g_argv) execv(g_exe_path, g_argv);

    // If execv fails, just exit
    exit(1);
}