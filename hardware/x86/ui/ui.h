#ifndef UI_H
#define UI_H

#include "platform.h"

void initThread(int argc, char ** argv);
void closeThread(void);
void setLED(led_color_t color);
bool buttonPressed(void);

#endif // UI_H