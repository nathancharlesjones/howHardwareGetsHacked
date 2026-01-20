#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "inc/hw_memmap.h"
#include "driverlib/eeprom.h"
#include "driverlib/gpio.h"
#include "driverlib/sysctl.h"
#include "driverlib/flash.h"

#include "messages.h"
#include "uart.h"
#include "dataFormats.h"
#include "platform.h"

#define UNLOCK_EEPROM_LOC 0x7C0

#define FEATURE_END 0x7C0
#define FEATURE1_LOC (FEATURE_END - FEATURE_SIZE)
#define FEATURE2_LOC (FEATURE_END - 2*FEATURE_SIZE)
#define FEATURE3_LOC (FEATURE_END - 3*FEATURE_SIZE)

#define FOB_STATE_PTR 0x3FC00
#define FLASH_DATA_SIZE         \
  (sizeof(FLASH_DATA) % 4 == 0) \
      ? sizeof(FLASH_DATA)      \
      : sizeof(FLASH_DATA) + (4 - (sizeof(FLASH_DATA) % 4))

static uint8_t previous_sw_state = GPIO_PIN_4;
static uint8_t debounce_sw_state = GPIO_PIN_4;
static uint8_t current_sw_state = GPIO_PIN_4;

static void initHardware(int argc, char ** argv)
{
	// Ensure EEPROM peripheral is enabled
	SysCtlPeripheralEnable(SYSCTL_PERIPH_EEPROM0);
	EEPROMInit();

	// Initialize UART peripheral
	uart_init(HOST_UART);

	// Initialize board link UART
	uart_init(BOARD_UART);
}

void initHardware_car(int argc, char ** argv)
{
	initHardware(argc, argv);

	// Change LED color for car: red
	setLED(RED);
}

void initHardware_fob(int argc, char ** argv)
{
	initHardware(argc, argv);

	// Change LED color for fob: white
	setLED(WHITE);

	// Setup SW1
	GPIOPinTypeGPIOInput(GPIO_PORTF_BASE, GPIO_PIN_4);
	GPIOPadConfigSet(GPIO_PORTF_BASE, GPIO_PIN_4, GPIO_STRENGTH_4MA,
                   GPIO_PIN_TYPE_STD_WPU);
}

void readVar(uint8_t* dest, char* var)
{
	if(!strcmp(var, "unlock")) EEPROMRead((uint32_t *)dest, UNLOCK_EEPROM_LOC, UNLOCK_SIZE);
	else if(!strcmp(var, "feature1")) EEPROMRead((uint32_t *)dest, FEATURE1_LOC, FEATURE_SIZE);
	else if(!strcmp(var, "feature2")) EEPROMRead((uint32_t *)dest, FEATURE2_LOC, FEATURE_SIZE);
	else if(!strcmp(var, "feature3")) EEPROMRead((uint32_t *)dest, FEATURE3_LOC, FEATURE_SIZE);
	else if(!strcmp(var, "fob_state")) memcpy(dest, (FLASH_DATA *)FOB_STATE_PTR, sizeof(FLASH_DATA));
}

/**
 * @brief Function that erases and rewrites the non-volatile data to flash
 *
 * @param info Pointer to the flash data ram
 */
void saveFobState(FLASH_DATA *flash_data)
{
  FlashErase(FOB_STATE_PTR);
  FlashProgram((uint32_t *)flash_data, FOB_STATE_PTR, FLASH_DATA_SIZE);
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