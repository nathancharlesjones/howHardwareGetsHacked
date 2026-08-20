/******************************************************************************
 *
 * firmware.ld - Linker configuration file for TM4C bare metal (no bootloader)
 *
 * Copyright (c) 2013-2017 Texas Instruments Incorporated.  All rights reserved.
 * 
 * Modified for bare metal operation without bootloader.
 * This version starts code at 0x00000000 with vector table at the beginning.
 *
 *****************************************************************************/

MEMORY
{
    /* Full flash available - no bootloader */
    FLASH           (rx)    : ORIGIN = 0x00000000, LENGTH = 0x0003FC00  /* 255 KB */
    FLASH_CONFIG    (rx)    : ORIGIN = 0x0003FC00, LENGTH = 0x00000400  /* 1 KB */
    RAM             (rwx)   : ORIGIN = 0x20000000, LENGTH = 0x00008000
}

/* Top of stack (used by startup file). SP starts at, and can grow down from,
 * the true top of physical RAM - not a hand-picked reservation somewhere in
 * the middle of it. How much of that headroom the stack (and heap - see
 * hardware/tm4c/source/syscalls.c) actually need is a question for
 * testing/test_build_budgets.py to measure per build, not for this script
 * to guess at. */
_stack_top = ORIGIN(RAM) + LENGTH(RAM);
_estack = _stack_top;

SECTIONS
{
    /* Interrupt vector table — MUST be first */
    .isr_vector :
    {
        KEEP(*(.isr_vector))
    } > FLASH
    
    .text :
    {
        _text = .;
        /* Vector table MUST be first for bare metal */
        KEEP(*(.firmware_startup))
        *(.text*)
        *(.rodata*)
        
        /* Handle C++ exception tables */
        KEEP(*(.init))
        KEEP(*(.fini))
        
        _etext = .;
    } > FLASH

    /* Reserve space for config data stored in FLASH
    .flash_config (NOLOAD) :
    {
        . = ALIGN(4);
        KEEP(*(.flash_config))
        . = ALIGN(4);
    } > FLASH_CONFIG
    
    /* Discard ARM exception index - not needed for bare metal C code */
    /DISCARD/ :
    {
        *(.ARM.exidx*)
        *(.ARM.extab*)
    }

    .data : AT(ADDR(.text) + SIZEOF(.text))
    {
        _data = .;
        _ldata = LOADADDR (.data);
        *(vtable)
        *(.data*)
        _edata = .;
    } > RAM

    .bss :
    {
        _bss = .;
        *(.bss*)
        *(COMMON)
        _ebss = .;
        /* Heap starts here and grows up toward _estack; see _sbrk() in
         * hardware/tm4c/source/syscalls.c. */
        . = ALIGN(8);
        _end = .;
    } > RAM
}

_flash_config_start = ORIGIN(FLASH_CONFIG);