#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "inc/hw_ints.h"
#include "inc/hw_types.h"
#include "inc/hw_gpio.h"
#include "driverlib/pin_map.h"

#include "inc/hw_memmap.h"
#include "driverlib/eeprom.h"
#include "driverlib/gpio.h"
#include "driverlib/sysctl.h"
#include "driverlib/flash.h"

#include "messages.h"
#include "uart.h"
#include "dataFormats.h"
#include "platform.h"

#define FEATURE_START 0x700

extern uint8_t _flash_config_start;
#define FOB_STATE_PTR ((uintptr_t)&_flash_config_start)

#define FLASH_DATA_SIZE         \
 		(sizeof(FLASH_DATA) % 4 == 0) \
  	 		? sizeof(FLASH_DATA)      \
     		: sizeof(FLASH_DATA) + (4 - (sizeof(FLASH_DATA) % 4))

static uint8_t previous_sw_state = GPIO_PIN_4;
static uint8_t debounce_sw_state = GPIO_PIN_4;
static uint8_t current_sw_state = GPIO_PIN_4;

static void initHardware(int argc, char ** argv)
{

	// Set system clock (example: 16 MHz PIOSC)
	SysCtlClockSet(SYSCTL_SYSDIV_1 |
	               SYSCTL_USE_OSC |
	               SYSCTL_OSC_MAIN |
	               SYSCTL_XTAL_16MHZ);

	// Ensure EEPROM peripheral is enabled
	SysCtlPeripheralEnable(SYSCTL_PERIPH_EEPROM0);
	EEPROMInit();

	// Initialize UART peripheral
	uart_init(HOST_UART, argc, argv);

	// Initialize board link UART
	uart_init(BOARD_UART, argc, argv);

	// Enable GPIO Port F
	SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOF);
	while(!SysCtlPeripheralReady(SYSCTL_PERIPH_GPIOF));

	// Configure LED pins
	GPIOPinTypeGPIOOutput(GPIO_PORTF_BASE,
	    GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3);
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

	// Unlock PF4 for use when reading SW1
	HWREG(GPIO_PORTF_BASE + GPIO_O_LOCK) = GPIO_LOCK_KEY;
	HWREG(GPIO_PORTF_BASE + GPIO_O_CR) |= GPIO_PIN_4;
	HWREG(GPIO_PORTF_BASE + GPIO_O_LOCK) = 0;

	// Setup SW1
	GPIOPinTypeGPIOInput(GPIO_PORTF_BASE, GPIO_PIN_4);
	GPIOPadConfigSet(GPIO_PORTF_BASE, GPIO_PIN_4, GPIO_STRENGTH_4MA,
                   GPIO_PIN_TYPE_STD_WPU);
}

void loadFlag(uint8_t* dest, flag_t flag)
{
	EEPROMRead((uint32_t *)dest, (FEATURE_START + flag*FLAG_SIZE), FLAG_SIZE);
}

/**
 * @brief Function that erases and rewrites the non-volatile data to flash
 *
 * @param info Pointer to the flash data ram
 */
void loadFobState(FLASH_DATA *dest)
{
  memcpy(dest, (uint8_t*)FOB_STATE_PTR, sizeof(FLASH_DATA));
}

bool saveFobState(const FLASH_DATA *flash_data)
{
    if (FlashErase(FOB_STATE_PTR) != 0) return false;
    if (FlashProgram((uint32_t *)flash_data, FOB_STATE_PTR, FLASH_DATA_SIZE) != 0) return false;
    
    /*
    FLASH_DATA verify;
		memcpy(&verify, (void*)FOB_STATE_PTR, sizeof(FLASH_DATA));
		if (memcmp(&verify, flash_data, sizeof(FLASH_DATA)) != 0) return false;
		*/

    return true;
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
    pressed = (debounce_sw_state == current_sw_state);
  }
  previous_sw_state = current_sw_state;
  return pressed;    
}
