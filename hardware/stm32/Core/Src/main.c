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
#include <stdio.h>
#include "messages.h"
#include "platform.h"
#include "dataFormats.h"
#include "uart.h"
//#include "stm32f0xx.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* Sector 6 (0x08040000): persistent flash data for the application
   Binary layout depeonds on whether this is car or fob firmware */
#define FLASH_DATA_BASE 0x08040000U

/* Sector 7 (0x08060000): flags programmed externally via openocd.py.
   Binary layout (FLAG_SIZE bytes each): feature3, feature2, feature1, unlock. */
#define FLAGS_BASE 0x08060000U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
ADC_HandleTypeDef hadc1;

TIM_HandleTypeDef htim5;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
//static FLASH_DATA flash_data __attribute__((section(".flash_data")));

static UART_HandleTypeDef* const uart_base[2] = { [HOST_UART] = &huart2, [BOARD_UART] = &huart1 };
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_ADC1_Init(void);
static void MX_TIM5_Init(void);
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
  uart_init(BOARD_UART, argc, argv);
  //uart_init();
  uart_init(HOST_UART, argc, argv);

  setLED(OFF);
}

void initHardware_car(int argc, char ** argv)
{
  initHardware(argc, argv);
  MX_ADC1_Init();
  MX_TIM5_Init();
}

void initHardware_fob(int argc, char ** argv)
{
  initHardware(argc, argv);
}

void loadFlag(uint8_t* dest, flag_t flag)
{
  memcpy(dest, (const char *)(FLAGS_BASE + flag * FLAG_SIZE), FLAG_SIZE);
}

void load_flash(void *dest, size_t size)
{
  memcpy(dest, (uint8_t*)(FLASH_DATA_BASE), size);
}

/* -----------------------------------------------------------
   Flash Sector Helper (F411 Example)
   ----------------------------------------------------------- */
static uint32_t flash_sector_start(uint32_t sector)
{
  uint32_t start_addr[] = { [FLASH_SECTOR_0] = 0x08000000,
                            [FLASH_SECTOR_1] = 0x08004000,
                            [FLASH_SECTOR_2] = 0x08008000,
                            [FLASH_SECTOR_3] = 0x0800C000,
                            [FLASH_SECTOR_4] = 0x08010000,
                            [FLASH_SECTOR_5] = 0x08020000,
                            [FLASH_SECTOR_6] = 0x08040000,
                            [FLASH_SECTOR_7] = 0x08060000, };
  return start_addr[sector];
}

/* -----------------------------------------------------------
   Config Flash Write (Overwrite Whole Sector)
   ----------------------------------------------------------- */
void save_flash(const void *src, size_t size)
{
  FLASH_EraseInitTypeDef erase =
  {
      .TypeErase    = FLASH_TYPEERASE_SECTORS,
      .Sector       = FLASH_SECTOR_6,
      .NbSectors    = 1,
      .VoltageRange = FLASH_VOLTAGE_RANGE_3,
  };

  size_t flash_data_bytes = (size % 4 == 0) ? size : size + (4 - (size % 4));
  size_t flash_data_words = flash_data_bytes / 4;

  uint8_t padded_data[flash_data_bytes];
  memset(padded_data, FLASH_UNINITIALIZED, sizeof(padded_data));
  memcpy(padded_data, src, size);

  uint32_t sector_err = 0;
  HAL_FLASH_Unlock();

  if (HAL_FLASHEx_Erase(&erase, &sector_err) != HAL_OK)
  {
      HAL_FLASH_Lock();
  }
  else
  {
    // Program new config data
    const uint32_t *words = (const uint32_t *)padded_data;
    uint32_t addr = flash_sector_start(FLASH_SECTOR_6);

    for (size_t i = 0; i < flash_data_words; i++)
    {
        if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, addr, words[i]) != HAL_OK) break;
        addr += 4;
    }

    HAL_FLASH_Lock();
  }
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

void setLED(led_color_t color)
{
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, color == GREEN);
}

void restart(void){}

static void uart_flush_rx(UART_HandleTypeDef *huart)
{
    uint8_t dummy;

    // Clear overrun / framing / noise flags first
    __HAL_UART_CLEAR_OREFLAG(huart);
    __HAL_UART_CLEAR_FEFLAG(huart);
    __HAL_UART_CLEAR_NEFLAG(huart);
    __HAL_UART_CLEAR_PEFLAG(huart);

    // Drain RX FIFO / RDR
    while (__HAL_UART_GET_FLAG(huart, UART_FLAG_RXNE))
    {
        HAL_UART_Receive(huart, &dummy, 1, 0);
    }
}

void delay_ms(uint32_t ms)
{
  HAL_Delay(ms);
}

uint32_t getHardwareTime(void)
{
  return DWT->CYCCNT;
}

/**
 * @brief Initialize the UART interfaces.
 *
 * UART 0 is used to communicate with the host computer.
 */
void uart_init(hw_uart_t uart, int argc, char ** argv)
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

  // Clear out receive buffers
  uart_flush_rx(uart_base[uart]);
}

/**
 * @brief Check if there are characters available on a UART interface.
 *
 * @param uart is the base address of the UART port.
 * @return true if there is data available.
 * @return false if there is no data available.
 */
bool uart_avail(hw_uart_t uart)
{
    UART_HandleTypeDef *huart = uart_base[uart];

    // IDLE means discard & return false
    if (__HAL_UART_GET_FLAG(huart, UART_FLAG_IDLE))
    {
        volatile uint32_t tmp;
        tmp = huart->Instance->SR;  // read status
        tmp = huart->Instance->DR;  // read data (clears IDLE)
        (void)tmp;
        return false;
    }

    // Any RX error means discard & return false
    if (__HAL_UART_GET_FLAG(huart, UART_FLAG_ORE) ||
        __HAL_UART_GET_FLAG(huart, UART_FLAG_FE)  ||
        __HAL_UART_GET_FLAG(huart, UART_FLAG_NE)  ||
        __HAL_UART_GET_FLAG(huart, UART_FLAG_PE))
    {
        uart_flush_rx(huart);
        return false;
    }

    return __HAL_UART_GET_FLAG(huart, UART_FLAG_RXNE) != RESET;
}


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
void uart_writeb(hw_uart_t uart, uint8_t data)
{
  HAL_UART_Transmit(uart_base[uart], &data, 1, HAL_MAX_DELAY);
}

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
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI|RCC_OSCILLATORTYPE_LSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.LSIState = RCC_LSI_ON;
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
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{

  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  ADC_ChannelConfTypeDef sConfig = {0};

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Configure the global features of the ADC (Clock, Resolution, Data Alignment and number of conversion)
  */
  hadc1.Instance = ADC1;
  hadc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
  hadc1.Init.Resolution = ADC_RESOLUTION_12B;
  hadc1.Init.ScanConvMode = DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 1;
  hadc1.Init.DMAContinuousRequests = DISABLE;
  hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure for the selected ADC regular channel its corresponding rank in the sequencer and its sample time.
  */
  sConfig.Channel = ADC_CHANNEL_VREFINT;
  sConfig.Rank = 1;
  sConfig.SamplingTime = ADC_SAMPLETIME_3CYCLES;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC1_Init 2 */

  /* USER CODE END ADC1_Init 2 */

}

/**
  * @brief TIM5 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM5_Init(void)
{

  /* USER CODE BEGIN TIM5_Init 0 */

  /* USER CODE END TIM5_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_IC_InitTypeDef sConfigIC = {0};

  /* USER CODE BEGIN TIM5_Init 1 */

  /* USER CODE END TIM5_Init 1 */
  htim5.Instance = TIM5;
  htim5.Init.Prescaler = 0;
  htim5.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim5.Init.Period = 4294967295;
  htim5.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim5.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim5) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim5, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_IC_Init(&htim5) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim5, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigIC.ICPolarity = TIM_INPUTCHANNELPOLARITY_RISING;
  sConfigIC.ICSelection = TIM_ICSELECTION_DIRECTTI;
  sConfigIC.ICPrescaler = TIM_ICPSC_DIV1;
  sConfigIC.ICFilter = 0;
  if (HAL_TIM_IC_ConfigChannel(&htim5, &sConfigIC, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIMEx_RemapConfig(&htim5, TIM_TIM5_LSI) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM5_Init 2 */

  /* USER CODE END TIM5_Init 2 */

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
