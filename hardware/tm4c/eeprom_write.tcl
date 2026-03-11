# eeprom_write.tcl
#
# Writes flag data to TM4C EEPROM via the EEPROM controller registers.
# Flag bytes never touch target RAM; data is carried in the $FLAG_DATA Tcl
# variable (a list of 64 little-endian 32-bit words) set by the caller.
#
# Prerequisites:
#   - Target must be halted
#   - $FLAG_DATA must be set before this script is invoked (64 words)
#
# flags.bin layout written to EEPROM (FLAG_SIZE=64 bytes = 16 words per block):
#   words  0-15  (FEATURE3, flag_t=0) -> block 28, EEPROM addr 0x700
#   words 16-31  (FEATURE2, flag_t=1) -> block 29, EEPROM addr 0x740
#   words 32-47  (FEATURE1, flag_t=2) -> block 30, EEPROM addr 0x780
#   words 48-63  (UNLOCK,   flag_t=3) -> block 31, EEPROM addr 0x7C0

# --- Register addresses ---
set RCGCEEPROM  0x400FE658
set SREEPROM    0x400FE558
set EEBLOCK     0x400AF010
set EEOFFSET    0x400AF014
set EERDWR      0x400AF018
set EEDONE      0x400AF020
set EESUPP      0x400AF024

# EEDONE.WORKING bit; EESUPP.ERETRY and PRETRY bits
set WORKING_BIT 0x1
set RETRY_BITS  0xC

proc wait_eeprom_ready { label } {
    global EEDONE WORKING_BIT
    set timeout 10000
    while { [expr { [mrw $EEDONE] & $::WORKING_BIT }] != 0 } {
        incr timeout -1
        if { $timeout <= 0 } { error "EEPROM timeout: $label" }
    }
}

# --- Enable EEPROM peripheral clock and wait for power-up init ---
mww $RCGCEEPROM 0x1
wait_eeprom_ready "power-up"

# --- Handle recovery mode (EESUPP.ERETRY or PRETRY set after certain failures) ---
if { [expr { [mrw $EESUPP] & $RETRY_BITS }] != 0 } {
    mww $SREEPROM 0x1
    sleep 1
    mww $SREEPROM 0x0
    sleep 5
    mww $RCGCEEPROM 0x1
    wait_eeprom_ready "post-reset"
    if { [expr { [mrw $EESUPP] & $RETRY_BITS }] != 0 } {
        error "EEPROM failed to initialize (EESUPP=[mrw $EESUPP])"
    }
}

# --- Write one EEPROM block (16 words) from $FLAG_DATA starting at $word_base ---
proc write_flag_block { block word_base } {
    global EEBLOCK EEOFFSET EERDWR
    mww $EEBLOCK $block
    for { set i 0 } { $i < 16 } { incr i } {
        set word [lindex $::FLAG_DATA [expr { $word_base + $i }]]
        mww $EEOFFSET $i
        mww $EERDWR   $word
        wait_eeprom_ready "block=$block offset=$i"
    }
}

write_flag_block 28  0   ;# FEATURE3
write_flag_block 29 16   ;# FEATURE2
write_flag_block 30 32   ;# FEATURE1
write_flag_block 31 48   ;# UNLOCK

echo "EEPROM flags written successfully"
