#ifndef PLATFORM_H
#define PLATFORM_H

#include "dataFormats.h"

#define FLASH_PAIRED 0x00
#define FLASH_UNPAIRED 0xFF

typedef enum { OFF, RED, GREEN, WHITE } led_color_t;

void initHardware_car(int argc, char ** argv);
void initHardware_fob(int argc, char ** argv);
void readVar(uint8_t* dest, char * var);
bool saveFobState(const FLASH_DATA *flash_data);
void setLED(led_color_t color);
bool buttonPressed(void);

#endif // PLATFORM_H