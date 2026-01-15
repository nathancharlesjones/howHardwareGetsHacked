#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "inc/hw_memmap.h"
#include "driverlib/eeprom.h"
#include "driverlib/gpio.h"
#include "driverlib/sysctl.h"

#include "board_link.h"
#include "uart.h"
#include "feature_list.h"

#include "platform.h"

#define UNLOCK_EEPROM_LOC 0x7C0
#define FEATURE_END 0x7C0
#define FEATURE1_LOC (FEATURE_END - FEATURE_SIZE)
#define FEATURE2_LOC (FEATURE_END - 2*FEATURE_SIZE)
#define FEATURE3_LOC (FEATURE_END - 3*FEATURE_SIZE)

static uint8_t previous_sw_state = GPIO_PIN_4;
static uint8_t debounce_sw_state = GPIO_PIN_4;
static uint8_t current_sw_state = GPIO_PIN_4;

static void initHardware(void)
{
	// Ensure EEPROM peripheral is enabled
	SysCtlPeripheralEnable(SYSCTL_PERIPH_EEPROM0);
	EEPROMInit();

	// Initialize UART peripheral
	uart_init();

	// Initialize board link UART
	setup_board_link();
}

void initHardware_car(void)
{
	initHardware();

	// Change LED color for car: red
	setLED(RED);
}

void initHardware_fob(void)
{
	initHardware();

	// Change LED color for fob: white
	setLED(WHITE);

	// Setup SW1
	GPIOPinTypeGPIOInput(GPIO_PORTF_BASE, GPIO_PIN_4);
	GPIOPadConfigSet(GPIO_PORTF_BASE, GPIO_PIN_4, GPIO_STRENGTH_4MA,
                   GPIO_PIN_TYPE_STD_WPU);
}

void readVar(uint8_t* dest, char* var, size_t size)
{
	if(!strcmp(var, "unlock")) EEPROMRead((uint32_t *)dest, UNLOCK_EEPROM_LOC, size);
	else if(!strcmp(var, "feature1")) EEPROMRead((uint32_t *)dest, FEATURE1_LOC, size);
	else if(!strcmp(var, "feature2")) EEPROMRead((uint32_t *)dest, FEATURE2_LOC, size);
	else if(!strcmp(var, "feature3")) EEPROMRead((uint32_t *)dest, FEATURE3_LOC, size);
}

void storeVar(uint8_t* src, char* var, size_t size)
{
	if(!strcmp(var, "flash_data"))
	{
		FlashErase(FOB_STATE_PTR);
		FlashProgram((uint32_t *)flash_data, FOB_STATE_PTR, FLASH_DATA_SIZE);
	}
}

void setLED(led_color_t color)
{
	uint32_t red = 0, green = 0, blue = 0;
	
	switch(color)
	{
	case RED:
		red = GPIO_PIN_1;
		break;
	case GREEN:
		green = GPIO_PIN_3;
		break;
	case WHITE:
		red = GPIO_PIN_1;
		green = GPIO_PIN_3;
		blue = GPIO_PIN_2;
		break;
	case OFF: // Intentional fall-through
	default:
		// Do nothing; default is LED off
		break;
	}

	GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1, red); // r
	GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_3, green); // g
	GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_2, blue); // b
}

bool buttonPressed(void)
{
	bool pressed = false;
	current_sw_state = GPIOPinRead(GPIO_PORTF_BASE, GPIO_PIN_4);
    if ((current_sw_state != previous_sw_state) && (current_sw_state == 0))
    {
      // Debounce switch
      for (int i = 0; i < 10000; i++)
        ;
      debounce_sw_state = GPIOPinRead(GPIO_PORTF_BASE, GPIO_PIN_4);
      previous_sw_state = current_sw_state;
      pressed = (debounce_sw_state == current_sw_state);
    }
    return pressed;
    
}