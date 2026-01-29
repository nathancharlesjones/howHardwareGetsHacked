#ifndef DATA_FORMATS_H
#define DATA_FORMATS_H

#include <stdint.h>

#define UNLOCK_SIZE 64

#define NUM_FEATURES 3
#define FEATURE_SIZE 64

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
__attribute__((aligned(4)))
{
  uint8_t paired;
  PAIR_PACKET pair_info;
  FEATURE_DATA feature_info;
} FLASH_DATA;

#endif // DATA_FORMATS_H