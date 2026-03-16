# eeprom.tcl
#
# TM4C EEPROM read/write via the EEPROM controller registers.
# Flag bytes never touch target RAM.
#
# Usage (OpenOCD batch or telnet):
#   Write: script eeprom.tcl; eeprom_write flags.bin     0x700 256
#   Read:  script eeprom.tcl; eeprom_read  flags_dump.bin 0x700 256
#
# Prerequisites:
#   - Target must be halted with 'halt' (not 'reset halt' — after a reset the
#     firmware has not yet enabled RCGCEEPROM, so register accesses bus-fault)
#
# flags.bin layout (FLAG_SIZE=64 bytes = 16 words per block):
#   words  0-15  (FEATURE3, flag_t=0) -> block 28, EEPROM addr 0x700
#   words 16-31  (FEATURE2, flag_t=1) -> block 29, EEPROM addr 0x740
#   words 32-47  (FEATURE1, flag_t=2) -> block 30, EEPROM addr 0x780
#   words 48-63  (UNLOCK,   flag_t=3) -> block 31, EEPROM addr 0x7C0

# --- Register addresses ---
set RCGCEEPROM  0x400FE658   ;# Run-Mode Clock Gating Control
set PREEEPROM   0x400FEA58   ;# Peripheral Ready
set SREEPROM    0x400FE558   ;# Software Reset
set EESIZE      0x400AF000   ;# bits 15:0 = WORDCNT (total 32-bit words)
set EEBLOCK     0x400AF004
set EEOFFSET    0x400AF008
set EERDWR      0x400AF010
set EERDWRINC   0x400AF014   ;# Read/write with auto-increment of EEOFFSET
set EEDONE      0x400AF018
set EESUPP      0x400AF01C

# EEDONE.WORKING bit; EESUPP.ERETRY and PRETRY bits
set WORKING_BIT 0x1
set RETRY_BITS  0xC

proc wait_eeprom_ready { label } {
    set timeout 10000
    while { [expr { [mrw $::EEDONE] & $::WORKING_BIT }] != 0 } {
        incr timeout -1
        if { $timeout <= 0 } { error "EEPROM timeout: $label" }
    }
}

# Ensure the EEPROM peripheral clock is on.
#
# If the firmware has already enabled and initialized the EEPROM (RCGCEEPROM=1,
# PREEEPROM=1) we leave it alone — issuing SREEPROM reset triggers a flash-backed
# re-init that sets WORKING=1 and cannot complete while the debug interface is
# polling, creating a deadlock that requires a fragile resume/halt workaround.
# Only do the full TI EEPROMInit() reset sequence when we enable the clock ourselves.
proc eeprom_init {} {
    set was_enabled [expr { [mrw $::RCGCEEPROM] & 0x1 }]

    if { !$was_enabled } {
        mww $::RCGCEEPROM 0x1
        set timeout 10000
        while { [expr { [mrw $::PREEEPROM] & 0x1 }] == 0 } {
            incr timeout -1
            if { $timeout <= 0 } { error "EEPROM peripheral ready timeout" }
        }
        # Mandatory reset on first enable (mirrors TI's EEPROMInit)
        mww $::SREEPROM 0x1
        sleep 1
        mww $::SREEPROM 0x0
        mww $::RCGCEEPROM 0x1
        set timeout 10000
        while { [expr { [mrw $::PREEEPROM] & 0x1 }] == 0 } {
            incr timeout -1
            if { $timeout <= 0 } { error "EEPROM peripheral ready timeout (post-reset)" }
        }
        wait_eeprom_ready "init"
    }

    if { [expr { [mrw $::EESUPP] & $::RETRY_BITS }] != 0 } {
        error "EEPROM failed to initialize (EESUPP=[format 0x%08x [mrw $::EESUPP]])"
    }
}

# Write $length bytes from $filename to EEPROM starting at $start_addr.
# Example: eeprom_write build/flags.bin 0x700 256
proc eeprom_write { filename start_addr length } {
    set start  [expr { $start_addr }]
    set nbytes [expr { $length }]

    if { ($start  % 4) != 0 } { error "start_addr must be 4-byte aligned" }
    if { ($nbytes % 4) != 0 } { error "length must be a multiple of 4" }

    # Validate file size matches the declared length
    set fd [open $filename r]
    fconfigure $fd -translation binary
    set raw [read $fd]
    close $fd

    set file_bytes [string length $raw]
    if { $file_bytes != $nbytes } {
        error "file size mismatch: $filename is $file_bytes bytes, expected $nbytes"
    }

    eeprom_init

    # Validate the write fits within the physical EEPROM (EESIZE.WORDCNT * 4 bytes)
    set eeprom_bytes [expr { ([mrw $::EESIZE] & 0xFFFF) * 4 }]
    if { $start + $nbytes > $eeprom_bytes } {
        error "write exceeds EEPROM bounds: [format 0x%X [expr {$start + $nbytes}]] > [format 0x%X $eeprom_bytes]"
    }

    set nwords [expr { $nbytes / 4 }]

    mww $::EEBLOCK  [expr { $start / 64 }]
    mww $::EEOFFSET [expr { ($start % 64) / 4 }]

    for { set i 0 } { $i < $nwords } { incr i } {
        # Unpack little-endian word from raw file bytes
        set byte_i [expr { $i * 4 }]
        scan [string index $raw  $byte_i              ] %c b0
        scan [string index $raw [expr { $byte_i + 1 }]] %c b1
        scan [string index $raw [expr { $byte_i + 2 }]] %c b2
        scan [string index $raw [expr { $byte_i + 3 }]] %c b3
        set word [expr { $b0 | ($b1 << 8) | ($b2 << 16) | ($b3 << 24) }]

        # Mirrors TI's EEPROMProgram: write via EERDWRINC (auto-increments EEOFFSET),
        # wait for completion, then advance EEBLOCK if EEOFFSET wrapped.
        wait_eeprom_ready "pre-write word $i"
        mww $::EERDWRINC $word
        wait_eeprom_ready "post-write word $i"

        set remaining [expr { $nwords - $i - 1 }]
        if { $remaining > 0 && [mrw $::EEOFFSET] == 0 } {
            mww $::EEBLOCK [expr { [mrw $::EEBLOCK] + 1 }]
        }
    }

    echo "EEPROM write: $nbytes bytes from $filename -> [format 0x%X $start]"
}

# Read $length bytes from EEPROM starting at $start_addr; save binary to $filename.
# Example: eeprom_read flags_dump.bin 0x700 256
#
# Mirrors TI's EEPROMRead(): uses EERDWRINC (auto-increments EEOFFSET after each
# read) and increments EEBLOCK manually when EEOFFSET wraps to 0.  No WORKING
# check — TI's read path never checks WORKING.
proc eeprom_read { filename start_addr length } {
    set start  [expr { $start_addr }]
    set nbytes [expr { $length }]

    if { ($start  % 4) != 0 } { error "start_addr must be 4-byte aligned" }
    if { ($nbytes % 4) != 0 } { error "length must be a multiple of 4" }

    eeprom_init

    # Validate the read fits within the physical EEPROM
    set eeprom_bytes [expr { ([mrw $::EESIZE] & 0xFFFF) * 4 }]
    if { $start + $nbytes > $eeprom_bytes } {
        error "read exceeds EEPROM bounds: [format 0x%X [expr {$start + $nbytes}]] > [format 0x%X $eeprom_bytes]"
    }

    set nwords [expr { $nbytes / 4 }]
    set fd     [open $filename w]
    fconfigure $fd -translation binary

    mww $::EEBLOCK  [expr { $start / 64 }]
    mww $::EEOFFSET [expr { ($start % 64) / 4 }]

    for { set i 0 } { $i < $nwords } { incr i } {
        # EERDWRINC returns the word at EEBLOCK/EEOFFSET and auto-increments EEOFFSET
        set word [mrw $::EERDWRINC]

        puts -nonewline $fd [format "%c%c%c%c" \
            [expr {  $word        & 0xFF }] \
            [expr { ($word >>  8) & 0xFF }] \
            [expr { ($word >> 16) & 0xFF }] \
            [expr { ($word >> 24) & 0xFF }]]

        # When EEOFFSET wraps to 0 we've crossed a block boundary; advance EEBLOCK.
        # Skip on the last word — writing EEBLOCK with no following read would leave
        # the controller expecting a data access (per TI's comment in eeprom.c).
        set remaining [expr { $nwords - $i - 1 }]
        if { $remaining > 0 && [mrw $::EEOFFSET] == 0 } {
            mww $::EEBLOCK [expr { [mrw $::EEBLOCK] + 1 }]
        }
    }

    close $fd
    echo "EEPROM read: $nbytes bytes from [format 0x%X $start] -> $filename"
}

# suppress the proc-name return value that Jim Tcl would otherwise echo
return
