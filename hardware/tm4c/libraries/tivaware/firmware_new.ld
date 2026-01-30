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

_STACK_SIZE = 0x1C00;

MEMORY
{
    /* Full flash available - no bootloader */
    FLASH    (rx) : ORIGIN = 0x00000000, LENGTH = 0x00040000
    SRAM    (rwx) : ORIGIN = 0x20000000, LENGTH = 0x00008000
}

SECTIONS
{
    .text :
    {
        _text = .;
        /* Vector table MUST be first for bare metal */
        KEEP(*(.isr_vector))
        KEEP(*(.firmware_startup))
        *(.text*)
        *(.rodata*)
        
        /* Handle C++ exception tables */
        KEEP(*(.init))
        KEEP(*(.fini))
        
        _etext = .;
    } > FLASH
    
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
    } > SRAM

    .bss :
    {
        _bss = .;
        *(.bss*)
        *(COMMON)
        _ebss = .;
        /* Heap starts here */
        . = ALIGN(8);
        _end = .;
    } > SRAM

    /* Stack section reserves space at end of usable RAM */
    .stack (NOLOAD) :
    {
        . = ALIGN(16);
        _heap_end = .;          /* Heap limit */
        . += _STACK_SIZE;
        _stack_top = .;         /* Stack pointer starts here */
    } > SRAM
    
    /* Top of physical RAM */
    _estack = ORIGIN(SRAM) + LENGTH(SRAM);
}
