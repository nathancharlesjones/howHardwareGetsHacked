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

#define FLASH_DATA_FILENAME "flash_data.bin"

// Private variables
static led_color_t ledColor = OFF;
static char flash_data_file_path[PATH_MAX] = "";
static bool buttonWasPressed = false;
static pthread_t h_tuiThread;

// Function prototypes
static void* tuiThread(void* data);

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
        snprintf(flash_data_file_path, PATH_MAX, "%s/%s", dir, FLASH_DATA_FILENAME);
    } else {
        /* Fallback to current directory */
        if (getcwd(exe_path, PATH_MAX) != NULL) {
            snprintf(flash_data_file_path, PATH_MAX, "%s/%s", exe_path, FLASH_DATA_FILENAME);
            int len = snprintf(flash_data_file_path, PATH_MAX, "%s/%s", exe_path, FLASH_DATA_FILENAME);
            if (len < 0 || (unsigned)len >= PATH_MAX)
            {
                // TODO: Is this the best response?
                fprintf(stderr, "Error: flash_data_file_path truncated or error occurred\n");
            }
        } else {
            /* Last resort */
            strncpy(flash_data_file_path, FLASH_DATA_FILENAME, PATH_MAX);
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
    
    // Add pthread
    pthread_create(&h_tuiThread, NULL, tuiThread, NULL);
}

static void* tuiThread(void* data)
{
    while(1)
    {
        char c = getchar();
        if(c == 'b') buttonWasPressed = true;
    }

    return NULL;
}

static void printCarData(void)
{
        
}

void initHardware_car(int argc, char ** argv)
{
    initHardware(argc, argv);
    setLED(RED);
    printCarData();
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

#define ESC "\x1b"

#define STR(x) #x
#define MV_TO_BEGINING_N_LINES_UP(n)    ESC"["STR(n)"F"
#define SEND_CURSOR_HOME                ESC"[H"
#define CLR_SCREEN_AFTER_CURSOR         ESC"[J"

#define SET_COLOR(color)                ESC"["color"m"
#define FOREGROUND_BLACK                "30"
#define FOREGROUND_RED                  "31"
#define FOREGROUND_GREEN                "32"
#define FOREGROUND_YELLOW               "33"
#define FOREGROUND_BLUE                 "34"
#define FOREGROUND_MAGENTA              "35"
#define FOREGROUND_CYAN                 "36"
#define FOREGROUND_WHITE                "37"
#define FOREGROUND_DEFAULT              "39"
#define BACKGROUND_BLACK                "40"
#define BACKGROUND_RED                  "41"
#define BACKGROUND_GREEN                "42"
#define BACKGROUND_YELLOW               "43"
#define BACKGROUND_BLUE                 "44"
#define BACKGROUND_MAGENTA              "45"
#define BACKGROUND_CYAN                 "46"
#define BACKGROUND_WHITE                "47"
#define BACKGROUND_DEFAULT              "49"
#define RESET_STYLES_AND_COLORS         ESC"[0m"

static void printFlashData(const FLASH_DATA* data)
{
    char* colorStr[] =
    {
        [OFF] = "Off",
        [RED] = "Red",
        [GREEN] = "Green",
        [WHITE] = "White"
    };

    char* foreground = NULL;
    char* background = NULL;

    switch(ledColor)
    {
    case RED:
        foreground = SET_COLOR(FOREGROUND_BLACK);
        background = SET_COLOR(BACKGROUND_RED);
        break;
    case GREEN:
        foreground = SET_COLOR(FOREGROUND_BLACK);
        background = SET_COLOR(BACKGROUND_GREEN);
        break;
    case WHITE:
        foreground = SET_COLOR(FOREGROUND_BLACK);
        background = SET_COLOR(BACKGROUND_WHITE);
        break;
    default: // Intentional fall-through
    case OFF:
        foreground = SET_COLOR(FOREGROUND_DEFAULT);
        background = SET_COLOR(BACKGROUND_DEFAULT);
        break;
    }

    printf(ESC SEND_CURSOR_HOME CLR_SCREEN_AFTER_CURSOR);
    printf("=====FOB DATA=====\n\r");
    printf("- LED color: %s%s%s%s\n\r", foreground, background, colorStr[ledColor], RESET_STYLES_AND_COLORS);
    printf("- Paired?: %s\n\r", data->paired == FLASH_PAIRED? "Yes" : "No");
    printf("- Pair info\n\r");
    printf("\t- Car ID:   %s\n\r", data->pair_info.car_id);
    printf("\t- Password: %s\n\r", data->pair_info.password);
    printf("\t- Pin:      %s\n\r", data->pair_info.pin);
    printf("- Feature info\n\r");
    printf("\t- Car ID:            %s\n\r", data->feature_info.car_id);
    printf("\t- # active features: %1d\n\r", data->feature_info.num_active);
    printf("\t- Active features:   [%1d, %1d, %1d]\n\r",    data->feature_info.features[0],
                                                            data->feature_info.features[1],
                                                            data->feature_info.features[2]);
    printf("==================\n\r>> ");
    
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
    printFlashData(&data);    
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
    
    //return (read == sizeof(FLASH_DATA));
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
    ledColor = color;
}

bool buttonPressed(void)
{
    if(buttonWasPressed)
    {
        buttonWasPressed = false;
        return true;
    }

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