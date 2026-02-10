#! /bin/bash

gcc guiTest.c gui_x86.c ../../../../libraries/microui/src/microui.c -I../../../../libraries/microui/src -I../../../include -I../../../../application/include -I. $(pkg-config --cflags --libs sdl2) -o guiTest