#include <stdbool.h>            // For true/false
#include <pthread.h>            // For pthread_t, pthread_create
#include <stdio.h>              // For getchar
#include <limits.h>             // For PATH_MAX
#include <stdlib.h>             // For exit
#include <libgen.h>             // For dirname
#include <unistd.h>             // For getcwd, access
#include <string.h>             // For strncpy, memcpy
#include <signal.h>             // For signal, SIGTERM, SIGINT
#include <time.h>               // For time (to seed PRNG)

#include "platform.h"
#include "uart.h"
#include "uart_sim.h"
#include "ui.h"

const char* FLASH_DATA_FILENAME = "flash_data.bin";
const char* FLAGS_FILENAME = "flags.bin";

// Private variables
static char flash_data_file_path[PATH_MAX] = "";
static char flags_file_path[PATH_MAX] = "";

// Function implementations
static void signal_handler(int sig)
{
    //(void)sig;
    uart_cleanup();
    closeThread();
    exit(0);
}

static void setup_data_file_path(char* dest, const char* filename, const char* argv0)
{
    char exe_path[PATH_MAX];
    char* dir;

    if (realpath(argv0, exe_path) != NULL) {
        dir = dirname(exe_path);
        snprintf(dest, PATH_MAX-1, "%.*s/%s",
                 (int)(PATH_MAX - 1 - strlen(filename) - 1), dir, filename);
    } else {
        if (getcwd(exe_path, PATH_MAX) != NULL) {
            snprintf(dest, PATH_MAX-1, "%.*s/%s",
                     (int)(PATH_MAX - 1 - strlen(filename) - 1), exe_path, filename);
        } else {
            strncpy(dest, filename, PATH_MAX-1);
        }
    }
}

static void initHardware(int argc, char ** argv)
{
    /* Set up state file path based on executable location */
    const char* exe = (argc > 0 && argv[0] != NULL) ? argv[0] : "./";
    setup_data_file_path(flash_data_file_path, FLASH_DATA_FILENAME, exe);
    setup_data_file_path(flags_file_path, FLAGS_FILENAME, exe);
    
    /* Set up signal handlers for clean shutdown */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    /* Initialize UARTs */
    uart_init(HOST_UART, argc, argv);
    uart_init(BOARD_UART, argc, argv);

    initThread(argc, argv);
}

static void create_default_car_state(void)
{
    CAR_FLASH_DATA default_state;
    memset(&default_state, 0xFF, sizeof(CAR_FLASH_DATA));
    
    saveCarState(&default_state);
}

void initHardware_car(int argc, char ** argv)
{
    initHardware(argc, argv);

#ifndef TEST_BUILD
    /* Create default fob state file if it doesn't exist */
    if (access(flash_data_file_path, F_OK) != 0)
#endif
    {
        create_default_car_state();
    }

    setLED(RED);
}

static void create_default_fob_state(void)
{
    FOB_FLASH_DATA default_state;
    memset(&default_state, 0xFF, sizeof(FOB_FLASH_DATA));
    
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
    FILE* fp = fopen(flags_file_path, "rb");
    if (!fp) return;
    fseek(fp, (long)(flag * FLAG_SIZE), SEEK_SET);
    size_t read = fread(dest, 1, FLAG_SIZE, fp);
    fclose(fp);

    if(read != FLAG_SIZE) exit(EXIT_FAILURE);
}

void load_flash(void* dest, size_t size)
{
    FILE* fp = fopen(flash_data_file_path, "rb");
    if (!fp) exit(EXIT_FAILURE);    
    size_t read = fread(dest, 1, size, fp);
    fclose(fp);
    if(read != size) exit(EXIT_FAILURE);
}

void save_flash(const void* src, size_t size)
{
    FILE* fp = fopen(flash_data_file_path, "wb");
    if (!fp) exit(EXIT_FAILURE);    
    size_t written = fwrite(src, 1, size, fp);
    fclose(fp);
    if(size != written) exit(EXIT_FAILURE);
}

#if defined(_WIN32)
#  include <bcrypt.h>
#elif defined(__APPLE__)
#  include <sys/random.h>   /* getentropy */
#else
#  include <sys/random.h>   /* getrandom */
#endif

void getPrngSeed(uint8_t *dest)
{
#if defined(_WIN32)
  BCryptGenRandom(NULL, dest, 32, BCRYPT_USE_SYSTEM_PREFERRED_RNG);
#elif defined(__APPLE__)
  getentropy(dest, 32);
#else
  getrandom(dest, 32, 0);
#endif
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