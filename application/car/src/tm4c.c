#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "driverlib/eeprom.h"
#include "driverlib/gpio.h"
#include "driverlib/sysctl.h"

#include "board_link.h"
#include "uart.h"

#define UNLOCK_EEPROM_LOC 0x7C0

void initHardware(void)
{
	// Ensure EEPROM peripheral is enabled
	SysCtlPeripheralEnable(SYSCTL_PERIPH_EEPROM0);
	EEPROMInit();

	// Change LED color: red
	GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1, GPIO_PIN_1); // r
	GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_2, 0); // b
	GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_3, 0); // g

	// Initialize UART peripheral
	uart_init();

	// Initialize board link UART
	setup_board_link();
}

void readVar(uint8_t* dest, char * var, size_t size)
{
	if(!strcmp(var, "unlock")) EEPROMRead((uint32_t *)dest, UNLOCK_EEPROM_LOC, size);
}