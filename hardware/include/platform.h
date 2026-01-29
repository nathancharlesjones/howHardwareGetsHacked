#ifndef PLATFORM_H
#define PLATFORM_H

#include "dataFormats.h"

#define FLASH_PAIRED 0x00
#define FLASH_UNPAIRED 0xFF

typedef enum { UNLOCK, FEATURE1 = 1, FEATURE2 = 2, FEATURE3 = 3 } flag_t;
typedef enum { OFF, RED, GREEN, WHITE } led_color_t;

void initHardware_car(int argc, char ** argv);
void initHardware_fob(int argc, char ** argv);
void loadFlag(uint8_t* dest, flag_t flag);
void loadFobState(FLASH_DATA *flash_data);
bool saveFobState(const FLASH_DATA *flash_data);
void setLED(led_color_t color);
bool buttonPressed(void);
void softwareReset(void);

#endif // PLATFORM_H