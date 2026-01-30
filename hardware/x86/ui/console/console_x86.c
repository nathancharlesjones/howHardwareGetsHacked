#include <stdbool.h>            // For true/false
#include <pthread.h>            // For pthread_t, pthread_create
#include <stdio.h>              // For getchar
#include <linux/limits.h>       // For PATH_MAX
#include <stdlib.h>             // For exit
#include <libgen.h>             // For dirname
#include <unistd.h>             // For getcwd, access, execv
#include <string.h>             // For strncpy, memcpy
#include <signal.h>             // For signal, SIGTERM, SIGINT

#include "ui.h"
#include "platform.h"

// Private variables
static led_color_t ledColor = OFF;
static bool buttonWasPressed = false;
static pthread_t h_consoleThread;
bool console_running = false;

// Function prototypes
static void* consoleThread(void* data);

void initThread(int argc, char ** argv)
{
    console_running = true;
    if (pthread_create(&h_consoleThread, NULL, consoleThread, NULL) != 0)
    {
        fprintf(stderr, "Failed to create GUI thread\n");
        console_running = false;
    }
}

static void* consoleThread(void* data)
{
    printf(">> ");

    while(1)
    {
        char c = getchar();
        if(c == 'b') buttonWasPressed = true;
    }

    return NULL;
}

void closeThread(void)
{
    if(console_running) pthread_join(h_consoleThread, NULL);
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

void setLED(led_color_t color)
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
    printf("====================\n\r");
    printf("= LED color: %s%s%5s%s =\n\r", foreground, background, colorStr[ledColor], RESET_STYLES_AND_COLORS);
    printf("====================\n\r>> ");
    
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