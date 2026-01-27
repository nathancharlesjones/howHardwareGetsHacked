/**
 * @file uart_x86.c
 * @brief x86 simulation UART implementation
 * 
 * Implements uart.h functions for x86 Linux using POSIX serial ports (termios).
 * Serial port paths are passed via command line arguments:
 *   host=/path/to/host/tty
 *   board=/path/to/board/tty
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>
#include <sys/select.h>
#include <sys/time.h>

#include "uart.h"

/*******************************************************************************
 * Configuration
 ******************************************************************************/
#define MAX_PATH_LEN 256
#define UART_BAUD_RATE B115200

/*******************************************************************************
 * File-local variables
 ******************************************************************************/
static int uart_fd[2] = { -1, -1 };
static char host_path[MAX_PATH_LEN] = "";
static char board_path[MAX_PATH_LEN] = "";

/*******************************************************************************
 * Internal helpers
 ******************************************************************************/
static int configure_serial_port(int fd)
{
    struct termios tty;
    
    if (tcgetattr(fd, &tty) != 0) {
        perror("tcgetattr");
        return -1;
    }
    
    /* Set baud rate */
    cfsetospeed(&tty, UART_BAUD_RATE);
    cfsetispeed(&tty, UART_BAUD_RATE);
    
    /* 8N1 mode */
    tty.c_cflag &= ~PARENB;        /* No parity */
    tty.c_cflag &= ~CSTOPB;        /* 1 stop bit */
    tty.c_cflag &= ~CSIZE;
    tty.c_cflag |= CS8;            /* 8 data bits */
    
    /* No hardware flow control */
    tty.c_cflag &= ~CRTSCTS;
    
    /* Enable receiver, ignore modem control lines */
    tty.c_cflag |= CREAD | CLOCAL;
    
    /* Raw input mode */
    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    
    /* Disable software flow control */
    tty.c_iflag &= ~(IXON | IXOFF | IXANY);
    
    /* Raw output mode */
    tty.c_oflag &= ~OPOST;
    
    /* Non-blocking read (poll with select instead) */
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;
    
    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        perror("tcsetattr");
        return -1;
    }
    
    /* Flush any pending data */
    tcflush(fd, TCIOFLUSH);
    
    return 0;
}

static int open_serial_port(const char* path)
{
    if (path == NULL || path[0] == '\0') {
        return -1;
    }
    
    int fd = open(path, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "Failed to open %s: %s\n", path, strerror(errno));
        return -1;
    }
    
    if (configure_serial_port(fd) != 0) {
        close(fd);
        return -1;
    }
    
    printf("Opened serial port: %s (fd=%d)\n", path, fd);
    return fd;
}

/*******************************************************************************
 * Cleanup
 ******************************************************************************/
void uart_cleanup(void)
{
    for (int i = 0; i < 2; i++) {
        if (uart_fd[i] >= 0) {
            close(uart_fd[i]);
            uart_fd[i] = -1;
        }
    }
}

/*******************************************************************************
 * UART API Implementation
 ******************************************************************************/

void uart_init(hw_uart_t uart, int argc, char ** argv)
{
    char* matchStr = (uart == HOST_UART) ? "host=" : "board=";
    char* path = (uart == HOST_UART) ? host_path : board_path;
    
    for (int i = 1; i < argc; i++)
    {
        if (strncmp(argv[i], matchStr, strlen(matchStr)) == 0)
        {
            strncpy(path, argv[i] + strlen(matchStr), MAX_PATH_LEN - 1);
            path[MAX_PATH_LEN - 1] = '\0';
        }
    }

    /* Close existing connection if any */
    if (uart_fd[uart] >= 0) {
        close(uart_fd[uart]);
        uart_fd[uart] = -1;
    }
    
    /* Open the serial port */
    if (path[0] != '\0') {
        uart_fd[uart] = open_serial_port(path);
    } else {
        const char* name = (uart == HOST_UART) ? "host" : "board";
        fprintf(stderr, "Warning: No %s= argument provided. %s_UART disabled.\n", 
                name, (uart == HOST_UART) ? "HOST" : "BOARD");
    }
}

bool uart_avail(hw_uart_t uart)
{
    if (uart_fd[uart] < 0) {
        return false;
    }
    
    fd_set read_fds;
    struct timeval tv = { .tv_sec = 0, .tv_usec = 0 };
    
    FD_ZERO(&read_fds);
    FD_SET(uart_fd[uart], &read_fds);
    
    int result = select(uart_fd[uart] + 1, &read_fds, NULL, NULL, &tv);
    
    return (result > 0 && FD_ISSET(uart_fd[uart], &read_fds));
}

int32_t uart_readb(hw_uart_t uart)
{
    if (uart_fd[uart] < 0) {
        return -1;
    }
    
    uint8_t byte;
    
    /* Block until a byte is available */
    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(uart_fd[uart], &read_fds);
    
    /* Wait indefinitely for data */
    int result = select(uart_fd[uart] + 1, &read_fds, NULL, NULL, NULL);
    if (result <= 0) {
        return -1;
    }
    
    ssize_t n = read(uart_fd[uart], &byte, 1);
    if (n == 1) {
        return (int32_t)byte;
    }
    
    return -1;
}

uint32_t uart_read(hw_uart_t uart, uint8_t* buf, uint32_t n)
{
    if (uart_fd[uart] < 0 || buf == NULL) {
        return 0;
    }
    
    uint32_t total_read = 0;
    
    while (total_read < n) {
        int32_t byte = uart_readb(uart);
        if (byte < 0) {
            break;
        }
        buf[total_read++] = (uint8_t)byte;
    }
    
    return total_read;
}

uint32_t uart_readline(hw_uart_t uart, uint8_t* buf)
{
    if (uart_fd[uart] < 0 || buf == NULL) {
        return 0;
    }
    
    uint32_t read_count = 0;
    uint8_t c;
    
    do {
        int32_t byte = uart_readb(uart);
        if (byte < 0) {
            break;
        }
        c = (uint8_t)byte;
        
        if ((c != '\r') && (c != '\n') && (c != 0x0D)) {
            buf[read_count++] = c;
        }
    } while ((c != '\n') && (c != 0x0D));
    
    buf[read_count] = '\0';
    
    return read_count;
}

void uart_writeb(hw_uart_t uart, uint8_t data)
{
    if (uart_fd[uart] < 0) {
        return;
    }
    
    ssize_t written = 0;
    while (written < 1) {
        ssize_t n = write(uart_fd[uart], &data, 1);
        if (n > 0) {
            written += n;
        } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            perror("uart_writeb");
            return;
        }
        /* If EAGAIN, we retry */
    }
}

uint32_t uart_write(hw_uart_t uart, uint8_t* buf, uint32_t len)
{
    if (uart_fd[uart] < 0 || buf == NULL) {
        return 0;
    }
    
    uint32_t total_written = 0;
    
    while (total_written < len) {
        ssize_t n = write(uart_fd[uart], buf + total_written, len - total_written);
        if (n > 0) {
            total_written += n;
        } else if (n < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                /* Non-blocking write would block, retry */
                usleep(100);
                continue;
            }
            perror("uart_write");
            break;
        }
    }
    
    return total_written;
}

/*******************************************************************************
 * Additional utilities for GUI (board UART reconnection)
 ******************************************************************************/
bool uart_reconnect_board(const char* new_path)
{
    if (new_path == NULL || new_path[0] == '\0') {
        return false;
    }
    
    /* Close existing board connection if open */
    if (uart_fd[BOARD_UART] >= 0) {
        close(uart_fd[BOARD_UART]);
        uart_fd[BOARD_UART] = -1;
    }
    
    /* Update path and reopen */
    strncpy(board_path, new_path, MAX_PATH_LEN - 1);
    board_path[MAX_PATH_LEN - 1] = '\0';
    
    uart_fd[BOARD_UART] = open_serial_port(board_path);
    
    return (uart_fd[BOARD_UART] >= 0);
}

const char* uart_get_board_path(void)
{
    return board_path;
}

const char* uart_get_host_path(void)
{
    return host_path;
}
