#ifndef CONFIG_H
#define CONFIG_H

// Choose exactly ONE
#define BUILD_PROD 1
// #define BUILD_TEST 1

// In testing files add:
// #if !BUILD_TEST
// #error "Testing file included in non-test build"
// #endif

// In production files add:
// #if !BUILD_PROD
// #error "Production file included in non-prod build"
// #endif

#ifdef ROLE_CAR
#define OBJ_T          car_t
#define OBJ_INSTANCE   car_instance
#define OBJ_INIT       car_init
#define OBJ_TICK       car_tick
#elif ROLE_FOB
#define OBJ_T          fob_t
#define OBJ_INSTANCE   fob_instance
#define OBJ_INIT       fob_init
#define OBJ_TICK       fob_tick
#else
#error "Unknown role"
#endif

#endif // CONFIG_H