#ifndef DATA_FORMATS_H
#define DATA_FORMATS_H

#include <stdint.h>
#include <stdbool.h>

#define FLAG_SIZE 64

#define NUM_FEATURES 3

// Defines a struct for the format of a pairing message
typedef struct
{
  char car_id[11];
  uint8_t key[16];
  char pin[7];
} PAIR_PACKET;

// Defines a struct for the format of an unlock message
typedef struct __attribute__((packed))
{
  uint8_t fob_id;
  uint16_t counter;
  uint8_t mac[8];
} UNLOCK_PACKET;

// Buffer layout for building an unlock message and computing its CMAC.
// The MAC field in UNLOCK_PACKET is 8 bytes, but AES_CMAC_digest always writes
// 16 bytes, so mac_overflow holds the upper half that is never transmitted.
typedef struct __attribute__((packed)) {
  uint8_t magic;
  uint8_t length;
  UNLOCK_PACKET payload;
  uint8_t mac_overflow[8];
} UNLOCK_MSG_BUF;

// Defines a struct for the format of start message
typedef struct
{
  char car_id[11];
  uint8_t num_active;
  uint8_t features[NUM_FEATURES];
} FEATURE_DATA;

// Defines a struct for storing the fob state in flash
typedef struct
__attribute__((aligned(4)))
{
  uint8_t paired;
  uint16_t rolling_counter;
  PAIR_PACKET pair_info;
  FEATURE_DATA feature_info;
} FOB_FLASH_DATA;

// Defines a struct for storing the car state in flash
typedef struct
__attribute__((aligned(4)))
{
  uint16_t fob_counter_values[256];
} CAR_FLASH_DATA;

#endif // DATA_FORMATS_H