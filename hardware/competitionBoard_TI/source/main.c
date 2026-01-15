#include "inc/hw_memmap.h"

uint32_t BOART_UART = ((uint32_t)UART1_BASE);
uint32_t HOST_UART = ((uint32_t)UART0_BASE);

void main(void)
{
	runTheApplication();
}