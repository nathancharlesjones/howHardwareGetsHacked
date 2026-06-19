#ifndef PLATFORM_H
#define PLATFORM_H

#include "dataFormats.h"

#define FLASH_PAIRED 0x01
#define FLASH_UNINITIALIZED 0xFF

typedef enum { FEATURE3 = 0, FEATURE2 = 1, FEATURE1 = 2, UNLOCK = 3 } flag_t;
typedef enum { OFF, RED, GREEN, WHITE } led_color_t;

void initHardware_car(int argc, char ** argv);
void initHardware_fob(int argc, char ** argv);
void loadFlag(uint8_t* dest, flag_t flag);
void loadFobState(FOB_FLASH_DATA *fob_data);
void saveFobState(const FOB_FLASH_DATA *fob_data);
void setLED(led_color_t color);
bool buttonPressed(void);
void getPrngSeed(uint8_t * dest);

#endif // PLATFORM_H