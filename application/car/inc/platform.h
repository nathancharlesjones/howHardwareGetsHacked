#ifndef PLATFORM_H
#define PLATFORM_H

typedef enum { RED, GREEN } led_color_t;

void initHardware(void);
void readVar(uint8_t* dest, char * var, size_t size);
void setLED(led_color_t color);

#endif // PLATFORM_H