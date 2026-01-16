#ifndef PLATFORM_H
#define PLATFORM_H

#include "feature_list.h"

typedef enum { OFF, RED, GREEN, WHITE } led_color_t;

// Defines a struct for the format of a pairing message
typedef struct
{
  uint8_t car_id[8];
  uint8_t password[8];
  uint8_t pin[8];
} PAIR_PACKET;

// Defines a struct for the format of start message
typedef struct
{
  uint8_t car_id[8];
  uint8_t num_active;
  uint8_t features[NUM_FEATURES];
} FEATURE_DATA;

// Defines a struct for storing the state in flash
typedef struct
{
  uint8_t paired;
  PAIR_PACKET pair_info;
  FEATURE_DATA feature_info;
} FLASH_DATA;

void initHardware_car(int argc, char ** argv);
void initHardware_fob(int argc, char ** argv);
void readVar(uint8_t* dest, char * var, size_t size);
void saveFobState(FLASH_DATA *flash_data);
void setLED(led_color_t color);
bool buttonPressed(void);

#endif // PLATFORM_H