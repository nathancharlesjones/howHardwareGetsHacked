/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>
#include "messages.h"
#include "platform.h"
#include "dataFormats.h"
#include "uart.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#ifndef UNLOCK_FLAG
#define UNLOCK_FLAG   "default_unlock"
#endif
#ifndef FEATURE1_FLAG
#define FEATURE1_FLAG "default_feature1"
#endif
#ifndef FEATURE2_FLAG
#define FEATURE2_FLAG "default_feature2"
#endif
#ifndef FEATURE3_FLAG
#define FEATURE3_FLAG "default_feature3"
#endif

#define FLASH_DATA_BYTES         \
  (sizeof(FLASH_DATA) % 4 == 0) \
      ? sizeof(FLASH_DATA)      \
      : sizeof(FLASH_DATA) + (4 - (sizeof(FLASH_DATA) % 4))
#define FLASH_DATA_WORDS (FLASH_DATA_BYTES / 4)
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
const char unlock_flag[UNLOCK_SIZE]    = UNLOCK_FLAG;
const char feature1_flag[FEATURE_SIZE] = FEATURE1_FLAG;
const char feature2_flag[FEATURE_SIZE] = FEATURE2_FLAG;
const char feature3_flag[FEATURE_SIZE] = FEATURE3_FLAG;

__attribute__((section(".flash_data")))
FLASH_DATA flash_data = {0};

extern uint8_t __flash_data_start__;
extern uint8_t __flash_data_end__;

static UART_HandleTypeDef* const uart_base[2] = { [HOST_UART] = &huart2, [BOARD_UART] = &huart1 };
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
static void initHardware(int argc, char ** argv)
{
  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* Configure the system clock */
  SystemClock_Config();

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  
  //setup_board_link();
  uart_init(BOARD_UART);
  //uart_init();
  uart_init(HOST_UART);

  setLED(OFF);
}

void initHardware_car(int argc, char ** argv)
{
  initHardware(argc, argv);
}

void initHardware_fob(int argc, char ** argv)
{
  initHardware(argc, argv);

  char msg[] = "Initialization complete\n";
  uart_write(HOST_UART, (uint8_t*)msg, strlen(msg));
}

void readVar(uint8_t* dest, char * var)
{
  size_t dataSize = 0;

  char msg[] = "Inside readVar\n";
  uart_write(HOST_UART, (uint8_t*)msg, strlen(msg));

  if(!strcmp(var, "unlock"))
  {
    memcpy(dest, unlock_flag, UNLOCK_SIZE);
    dataSize = UNLOCK_SIZE;
  }
  else if(!strcmp(var, "feature1"))
  {
    memcpy(dest, feature1_flag, FEATURE_SIZE);
    dataSize = FEATURE_SIZE;
  }
  else if(!strcmp(var, "feature2"))
  {
    memcpy(dest, feature2_flag, FEATURE_SIZE);
    dataSize = FEATURE_SIZE;
  }
  else if(!strcmp(var, "feature3"))
  {
    memcpy(dest, feature3_flag, FEATURE_SIZE);
    dataSize = FEATURE_SIZE;
  }
  else if(!strcmp(var, "fob_state"))
  {
    char msg[] = "Fetching fob state\n";
    uart_write(HOST_UART, (uint8_t*)msg, strlen(msg));
    memcpy(dest, (uint8_t*)(&flash_data), sizeof(FLASH_DATA));
    dataSize = sizeof(FLASH_DATA);
  }

  char msg2[] = "Data is: ";
  uart_write(HOST_UART, (uint8_t*)msg2, strlen(msg2));
  uart_write(HOST_UART, dest, dataSize);
  uart_writeb(HOST_UART, '\n');
}

/* -----------------------------------------------------------
   Flash Sector Helper (F411 Example)
   ----------------------------------------------------------- */
static uint32_t get_flash_sector(uint32_t addr)
{
  if (addr < 0x08004000) return FLASH_SECTOR_0;
  if (addr < 0x08008000) return FLASH_SECTOR_1;
  if (addr < 0x0800C000) return FLASH_SECTOR_2;
  if (addr < 0x08010000) return FLASH_SECTOR_3;
  if (addr < 0x08020000) return FLASH_SECTOR_4;
  if (addr < 0x08040000) return FLASH_SECTOR_5;
  if (addr < 0x08060000) return FLASH_SECTOR_6;
  return FLASH_SECTOR_7;
}

/* -----------------------------------------------------------
   Config Flash Write (Overwrite Whole Sector)
   ----------------------------------------------------------- */
bool saveFobState(const FLASH_DATA *src)
{
  uint32_t base = (uint32_t)&__flash_data_start__;
  uint32_t end  = (uint32_t)&__flash_data_end__;
  uint32_t size = end - base;

  // Sanity check: config struct fits in sector
  if (sizeof(FLASH_DATA_BYTES) > size)
  {
      return false;
  }

  // Erase the sector that holds .config_flash
  uint32_t sector = get_flash_sector(base);
  FLASH_EraseInitTypeDef erase =
  {
      .TypeErase    = FLASH_TYPEERASE_SECTORS,
      .Sector       = sector,
      .NbSectors    = 1,
      .VoltageRange = FLASH_VOLTAGE_RANGE_3,
  };

  uint8_t padded_data[FLASH_DATA_BYTES];
  memset(padded_data, 0xFF, sizeof(padded_data));
  memcpy((FLASH_DATA*)(&padded_data), src, sizeof(FLASH_DATA));

  uint32_t sector_err = 0;
  HAL_FLASH_Unlock();

  if (HAL_FLASHEx_Erase(&erase, &sector_err) != HAL_OK)
  {
      HAL_FLASH_Lock();
      return false;
  }

  // Program new config data
  const uint32_t *words = (const uint32_t *)src;
  uint32_t addr = base;

  for (size_t i = 0; i < FLASH_DATA_WORDS; i++)
  {
      if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, addr, words[i]) != HAL_OK) {
          HAL_FLASH_Lock();
          return false;
      }
      addr += 4;
  }

  HAL_FLASH_Lock();
  return true;
}

void setLED(led_color_t color)
{
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, color == GREEN);
}

bool buttonPressed(void)
{
  static uint32_t history = 0;
  static bool latched = false;

  bool buttonValue = HAL_GPIO_ReadPin(B1_GPIO_Port, B1_Pin);

  history = (history << 1) |
            (buttonValue == GPIO_PIN_RESET);

  if (history == 0xFFFFFFFF && !latched) {
      latched = true;
      return true;        // button just pressed
  }

  if (history == 0x00000000) {
      latched = false;    // fully released
  }

  return false;
}

/**
 * @brief Initialize the UART interfaces.
 *
 * UART 0 is used to communicate with the host computer.
 */
void uart_init(hw_uart_t uart)
{
  switch(uart)
  {
  case HOST_UART:
    MX_USART2_UART_Init();
    break;
  case BOARD_UART:
    MX_USART1_UART_Init();
    break;
  }
}

/**
 * @brief Check if there are characters available on a UART interface.
 *
 * @param uart is the base address of the UART port.
 * @return true if there is data available.
 * @return false if there is no data available.
 */
bool uart_avail(hw_uart_t uart) { return (__HAL_UART_GET_FLAG(uart_base[uart], UART_FLAG_RXNE) != RESET); }

/**
 * @brief Read a byte from a UART interface.
 *
 * @param uart is the base address of the UART port to read from.
 * @return the character read from the interface.
 */
int32_t uart_readb(hw_uart_t uart)
{
  int32_t c;
  HAL_UART_Receive(uart_base[uart], (uint8_t*)(&c), 1, HAL_MAX_DELAY);
  return c;
}

/**
 * @brief Read a sequence of bytes from a UART interface.
 *
 * @param uart is the base address of the UART port to read from.
 * @param buf is a pointer to the destination for the received data.
 * @param n is the number of bytes to read.
 * @return the number of bytes read from the UART interface.
 */
uint32_t uart_read(hw_uart_t uart, uint8_t *buf, uint32_t n)
{
  HAL_UART_Receive(uart_base[uart], buf, n, HAL_MAX_DELAY);
  return n;
}

/**
 * @brief Read a line (terminated with '\n') from a UART interface.
 *
 * @param uart is the base address of the UART port to read from.
 * @param buf is a pointer to the destination for the received data.
 * @return the number of bytes read from the UART interface.
 */
uint32_t uart_readline(hw_uart_t uart, uint8_t *buf) {
  uint32_t read = 0;
  uint8_t c;
  UART_HandleTypeDef* base = uart_base[uart];

  do
  {
    HAL_UART_Receive(base, &c, 1, HAL_MAX_DELAY);

    if ((c != '\r') && (c != '\n') && (c != 0xD))
    {
      buf[read] = c;
      read++;
    }

  } while ((c != '\n') && (c != 0xD));

  buf[read] = '\0';

  return read;
}

/**
 * @brief Write a byte to a UART interface.
 *
 * @param uart is the base address of the UART port to write to.
 * @param data is the byte value to write.
 */
void uart_writeb(hw_uart_t uart, uint8_t data) { HAL_UART_Transmit(uart_base[uart], &data, 1, HAL_MAX_DELAY); }

/**
 * @brief Write a sequence of bytes to a UART interface.
 *
 * @param uart is the base address of the UART port to write to.
 * @param buf is a pointer to the data to send.
 * @param len is the number of bytes to send.
 * @return the number of bytes written.
 */
uint32_t uart_write(hw_uart_t uart, uint8_t *buf, uint32_t len)
{
  HAL_UART_Transmit(uart_base[uart], buf, len, HAL_MAX_DELAY);
  return len;
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 4;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
