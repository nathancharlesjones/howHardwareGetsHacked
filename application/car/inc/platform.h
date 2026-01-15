#ifndef PLATFORM_H
#define PLATFORM_H

typedef enum { OFF, RED, GREEN, WHITE } led_color_t;

void initHardware_car(void);
void initHardware_fob(void);
void readVar(uint8_t* dest, char * var, size_t size);
void setLED(led_color_t color);
bool buttonPressed(void);

#endif // PLATFORM_H