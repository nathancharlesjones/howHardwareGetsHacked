#include "main.h"
#include "board_link.h"
#include "platform.h"
#include "feature_list.h"
#include "uart.h"

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

static void initHardware(int argc, char ** argv)
{
	/* Reset of all peripherals, Initializes the Flash interface and the Systick. */
	HAL_Init();

	/* Configure the system clock */
	SystemClock_Config();

  	/* Initialize all configured peripherals */
  	MX_GPIO_Init();
  	MX_USART1_UART_Init();
  	MX_USART2_UART_Init();
}

void initHardware_car(void){}
void initHardware_fob(void){}
void readVar(uint8_t* dest, char * var, size_t size){}
void saveFobState(FLASH_DATA *flash_data){}
void setLED(led_color_t color){}
bool buttonPressed(void){}