#include <stdbool.h>            // For true/false
#include <pthread.h>            // For pthread_t, pthread_create
#include <stdio.h>              // For getchar
#include <limits.h>             // For PATH_MAX
#include <stdlib.h>             // For exit
#include <libgen.h>             // For dirname
#include <unistd.h>             // For getcwd, access, execv
#include <string.h>             // For strncpy, memcpy
#include <signal.h>             // For signal, SIGTERM, SIGINT
#include <fcntl.h>              // For fcntl
#include <time.h>               // For struct timespec, nanosleep
#include <termios.h>

#include "ui.h"
#include "platform.h"

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

#define HIDE_CURSOR                     ESC"[?25l"
#define SHOW_CURSOR                     ESC"[?25h"

// Private variables
static led_color_t ledColor = OFF;
static bool buttonWasPressed = false;
static pthread_t h_consoleThread;
bool console_running = false;
static struct termios old_termios;

// Function prototypes
static void ensure_terminal(int argc, char **argv);
static void* consoleThread(void* data);
static void updateDisplay(void);
static void restore_terminal(void);
static void setup_terminal(void);

void initThread(int argc, char ** argv)
{
    ensure_terminal(argc, argv);

    console_running = true;
    if (pthread_create(&h_consoleThread, NULL, consoleThread, NULL) != 0)
    {
        fprintf(stderr, "Failed to create GUI thread\n");
        console_running = false;
    }
}

static void* consoleThread(void* data)
{
    // Make stdin non-blocking
    int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
    fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);

    // Disable line-buffering and echo
    setup_terminal();

    // Set up timer
    struct timespec ts;
    ts.tv_sec = 0;          // 0 seconds
    ts.tv_nsec = 1e9 / 20;  // 20 Hz (1e9 ns / 20)

    printf(HIDE_CURSOR);
    printf("Press (b) for button\n\r");

    while(1)
    {
        // Update screen
        updateDisplay();

        // Test for button press
        char c;
        ssize_t n = read(STDIN_FILENO, &c, 1);

        if (n > 0)
        {
            if (c == 'b') buttonWasPressed = true;
        }

        // 60 Hz frame rate
        nanosleep(&ts, NULL);
    }

    return NULL;
}

static void ensure_terminal(int argc, char **argv)
{
    if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO))
    {
        // Prevent infinite recursion
        if (getenv("IN_XTERM"))
            return;

        setenv("IN_XTERM", "1", 1);

        char **new_argv = calloc(argc + 9, sizeof(char *));
        int i = 0;

        new_argv[i++] = "xterm";
        new_argv[i++] = "-fa";
        new_argv[i++] = "Monospace";
        new_argv[i++] = "-fs";
        new_argv[i++] = "14";
        new_argv[i++] = "-T";
        new_argv[i++] = argv[0];
        new_argv[i++] = "-e";

        for (int a = 0; a < argc; a++)
            new_argv[i++] = argv[a];

        execvp("xterm", new_argv);

        perror("execvp xterm");
        exit(1);
    }
}

static void restore_terminal(void) {
    tcsetattr(STDIN_FILENO, TCSANOW, &old_termios);
}

static void setup_terminal(void) {
    struct termios t;
    tcgetattr(STDIN_FILENO, &old_termios);
    atexit(restore_terminal);

    t = old_termios;
    t.c_lflag &= ~(ICANON | ECHO);
    t.c_cc[VMIN] = 0;
    t.c_cc[VTIME] = 0;

    tcsetattr(STDIN_FILENO, TCSANOW, &t);
}

void closeThread(void)
{
    if(console_running)
    {
        pthread_join(h_consoleThread, NULL);
        restore_terminal();
        printf(SHOW_CURSOR);
    }
}

static void updateDisplay(void)
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

    printf("====================\n\r");
    printf("= LED color: %s%s%5s%s =\n\r", foreground, background, colorStr[ledColor], RESET_STYLES_AND_COLORS);
    printf("====================\n\r");
    printf(MV_TO_BEGINING_N_LINES_UP(3) CLR_SCREEN_AFTER_CURSOR);
    
}

void setLED(led_color_t newColor)
{
    ledColor = newColor;
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