#ifndef DATA_FORMATS_H
#define DATA_FORMATS_H

#include <stdint.h>
#include <stdbool.h>

#define UNLOCK_SIZE 64

#define NUM_FEATURES 3
#define FEATURE_SIZE 64

// Defines a struct for the format of a pairing message
typedef struct
{
  char car_id[11];
  char password[8];
  char pin[7];
} PAIR_PACKET;

// Defines a struct for the format of start message
typedef struct
{
  char car_id[11];
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