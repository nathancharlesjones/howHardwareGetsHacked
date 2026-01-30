#ifndef UI_H
#define UI_H

#include "platform.h"

void __attribute__((weak)) initThread(int argc, char ** argv);
void __attribute__((weak)) closeThread(void);
void __attribute__((weak)) setLED(led_color_t color);
bool __attribute__((weak)) buttonPressed(void);

#endif // UI_H