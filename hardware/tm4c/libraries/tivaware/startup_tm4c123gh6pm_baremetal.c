/*
 * startup_tm4c123gh6pm_baremetal.c - Minimal startup code for TM4C without bootloader
 * 
 * This startup code is needed when NOT using a bootloader.
 * It initializes the vector table, copies .data from Flash to RAM,
 * zeros the .bss section, and calls main().
 */

#include <stdint.h>

// Linker script symbols
extern uint32_t _etext;     // End of .text in Flash
extern uint32_t _data;      // Start of .data in RAM
extern uint32_t _edata;     // End of .data in RAM
extern uint32_t _bss;       // Start of .bss in RAM
extern uint32_t _ebss;      // End of .bss in RAM
extern uint32_t _ldata;     // Load address of .data in Flash
extern uint32_t _stack_top; // Top of stack

// Main function
extern int main(void);

// Default exception handler
void Default_Handler(void)
{
    while(1) {
        __asm volatile ("wfi");
    }
}

// Weak aliases for all handlers point to Default_Handler
void Reset_Handler(void);
void NMI_Handler(void)          __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)          __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)      __attribute__((weak, alias("Default_Handler")));

// Vector table
__attribute__((section(".isr_vector"), used))
void (* const g_pfnVectors[])(void) =
{
    (void (*)(void))((uint32_t)&_stack_top), // Initial Stack Pointer
    Reset_Handler,                            // Reset Handler
    NMI_Handler,                              // NMI Handler
    HardFault_Handler,                        // Hard Fault Handler
    MemManage_Handler,                        // MPU Fault Handler
    BusFault_Handler,                         // Bus Fault Handler
    UsageFault_Handler,                       // Usage Fault Handler
    0,                                        // Reserved
    0,                                        // Reserved
    0,                                        // Reserved
    0,                                        // Reserved
    SVC_Handler,                              // SVCall Handler
    DebugMon_Handler,                         // Debug Monitor Handler
    0,                                        // Reserved
    PendSV_Handler,                           // PendSV Handler
    SysTick_Handler,                          // SysTick Handler
    
    // External Interrupts (first 16, add more as needed)
    Default_Handler,                          // GPIO Port A
    Default_Handler,                          // GPIO Port B
    Default_Handler,                          // GPIO Port C
    Default_Handler,                          // GPIO Port D
    Default_Handler,                          // GPIO Port E
    Default_Handler,                          // UART0 Rx and Tx
    Default_Handler,                          // UART1 Rx and Tx
    Default_Handler,                          // SSI0 Rx and Tx
    Default_Handler,                          // I2C0 Master and Slave
    Default_Handler,                          // PWM Fault
    Default_Handler,                          // PWM Generator 0
    Default_Handler,                          // PWM Generator 1
    Default_Handler,                          // PWM Generator 2
    Default_Handler,                          // Quadrature Encoder 0
    Default_Handler,                          // ADC Sequence 0
    Default_Handler,                          // ADC Sequence 1
    // ... add more interrupt vectors as needed
};

// Reset handler - entry point after reset
void Reset_Handler(void)
{
    uint32_t *src, *dst;
    
    // Copy .data section from Flash to RAM
    src = &_ldata;
    dst = &_data;
    while (dst < &_edata) {
        *dst++ = *src++;
    }
    
    // Zero out .bss section
    dst = &_bss;
    while (dst < &_ebss) {
        *dst++ = 0;
    }
    
    // Call main
    main();
    
    // If main returns, loop forever
    while (1) {
        __asm volatile ("wfi");
    }
}
