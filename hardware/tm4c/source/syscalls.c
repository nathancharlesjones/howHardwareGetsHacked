/**
 * Minimal syscalls implementation for TM4C (newlib stubs)
 * 
 * These are the minimum syscalls required when using functions like snprintf
 * that depend on newlib. Most of these are minimal stubs that just return
 * error values since we're running bare metal without an OS.
 */

#include <sys/stat.h>
#include <errno.h>

#undef errno
extern int errno;

// Heap management - used by malloc/free
char *__env[1] = { 0 };
char **environ = __env;

// Increase program data space (used by malloc)
void *_sbrk(int incr)
{
    extern char _end;           // Defined by linker (end of .bss section)
    extern char _estack;        // Defined by linker (true top of physical RAM)
    static char *heap_ptr = 0;
    char *prev_heap_ptr;

    if (heap_ptr == 0) {
        heap_ptr = &_end;
    }

    prev_heap_ptr = heap_ptr;

    // The linker no longer carves out a fixed reservation for the stack
    // (see firmware.ld) - there's nothing but _estack itself to check the
    // heap against here. This codebase doesn't call malloc() directly and
    // nothing on its current call paths reaches it either, so this is a
    // correctness fallback rather than an active concern; if that ever
    // changes, testing/test_build_budgets.py's worst-case stack figure is
    // what should be weighed against how much heap is actually in use, not
    // a number invented here.
    if (heap_ptr + incr > &_estack) {
        errno = ENOMEM;
        return (void *)-1;
    }

    heap_ptr += incr;
    return (void *)prev_heap_ptr;
}

// Exit program (called on exit())
void _exit(int status)
{
    // In bare metal, just loop forever
    while (1) {
        __asm volatile ("wfi");  // Wait for interrupt
    }
}

// Send signal to process (not applicable in bare metal)
int _kill(int pid, int sig)
{
    errno = EINVAL;
    return -1;
}

// Get process ID (not applicable in bare metal)
int _getpid(void)
{
    return 1;  // Return a constant PID
}

// Write to file descriptor
// Override this if you want printf to output to UART
int _write(int file, char *ptr, int len)
{
    // For now, just pretend we wrote it
    // TODO: Implement UART output here if needed
    return len;
}

// Close file (not applicable in bare metal)
int _close(int file)
{
    return -1;
}

// Status of open file (treat all files as character devices)
int _fstat(int file, struct stat *st)
{
    st->st_mode = S_IFCHR;  // Character device
    return 0;
}

// Query whether output stream is a terminal
int _isatty(int file)
{
    return 1;  // Pretend all file descriptors are terminals
}

// Set position in file
int _lseek(int file, int ptr, int dir)
{
    return 0;
}

// Read from file descriptor
int _read(int file, char *ptr, int len)
{
    // For now, return 0 (EOF)
    // TODO: Implement UART input here if needed
    return 0;
}

// If DEBUG is defined, TivaWare requires this error handler
#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ulLine)
{
    // Place a breakpoint here to catch errors
    while(1)
    {
    }
}
#endif
