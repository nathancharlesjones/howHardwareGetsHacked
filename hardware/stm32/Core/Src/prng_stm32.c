#include <string.h>

#include "main.h"
#include "aes_cmac.h"
#include "aes.h"
#include "secrets.h"

extern ADC_HandleTypeDef hadc1;
extern TIM_HandleTypeDef htim5;

static void entropy_hw_init(void)
{
    /* PA1 must be in analog mode for the floating-pin channel.
       GPIOA clock is already enabled in MX_GPIO_Init. */
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin  = GPIO_PIN_1;
    gpio.Mode = GPIO_MODE_ANALOG;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);

    HAL_TIM_IC_Start(&htim5, TIM_CHANNEL_4);
}

static uint32_t read_hsi_per_lsi(void)
{
    __HAL_TIM_CLEAR_FLAG(&htim5, TIM_FLAG_CC4);
    while (!__HAL_TIM_GET_FLAG(&htim5, TIM_FLAG_CC4));
    uint32_t t1 = HAL_TIM_ReadCapturedValue(&htim5, TIM_CHANNEL_4);
    __HAL_TIM_CLEAR_FLAG(&htim5, TIM_FLAG_CC4);
    while (!__HAL_TIM_GET_FLAG(&htim5, TIM_FLAG_CC4));
    uint32_t t2 = HAL_TIM_ReadCapturedValue(&htim5, TIM_CHANNEL_4);
    __HAL_TIM_CLEAR_FLAG(&htim5, TIM_FLAG_CC4);
    return t2 - t1;
}

/* ADC clock = PCLK2/4 = 84/4 = 21 MHz → period ≈ 47.6 ns.
   Temp sensor and VREFINT both require ≥10 µs minimum sample time
   (≈210 cycles at 21 MHz); 480 cycles satisfies that with margin. */
static uint16_t adc_single(uint32_t channel, uint32_t sampling_time)
{
    ADC_ChannelConfTypeDef sConfig = {0};
    sConfig.Channel      = channel;
    sConfig.Rank         = 1;
    sConfig.SamplingTime = sampling_time;
    HAL_ADC_ConfigChannel(&hadc1, &sConfig);
    HAL_ADC_Start(&hadc1);
    HAL_ADC_PollForConversion(&hadc1, HAL_MAX_DELAY);
    uint16_t val = (uint16_t)HAL_ADC_GetValue(&hadc1);
    HAL_ADC_Stop(&hadc1);
    return val;
}

static uint16_t read_adc_vref(void)
{
    return adc_single(ADC_CHANNEL_VREFINT,    ADC_SAMPLETIME_480CYCLES);
}

static uint16_t read_adc_temp(void)
{
    return adc_single(ADC_CHANNEL_TEMPSENSOR, ADC_SAMPLETIME_480CYCLES);
}

static uint16_t read_adc_float(void)
{
    return adc_single(ADC_CHANNEL_1,          ADC_SAMPLETIME_56CYCLES);
}

static struct AES_ctx s_seed_aes;
static void seed_encrypt(uint8_t *data) { AES_ECB_encrypt(&s_seed_aes, data); }

enum { VCC, TEMP, JITTER, FLOAT_PIN, NUM_SOURCES };

uint8_t getEntropySourceCount(void){ return NUM_SOURCES; }

const char * getEntropySourceName(uint8_t source_num)
{
    const static char* names[NUM_SOURCES] = { [VCC] = "vcc",
                                              [TEMP] = "temp",
                                              [JITTER] = "jitter",
                                              [FLOAT_PIN] = "float_pin"
                                            };
    return source_num < NUM_SOURCES ? names[source_num] : "Invalid source number";
}

uint16_t getEntropySourceSamples(uint8_t source_num, uint8_t num_samples, uint8_t* dest)
{
    const static uint8_t byte_widths[NUM_SOURCES] = { [VCC] = 2,
                                                      [TEMP] = 2,
                                                      [JITTER] = 4,
                                                      [FLOAT_PIN] = 2
                                                    };

    if( source_num >= getEntropySourceCount() ) return 0;
    uint8_t byte_width = byte_widths[source_num];
    uint8_t requested = num_samples;
    for( ; num_samples > 0; num_samples-- )
    {
        uint32_t sample;
        switch(source_num)
        {
            case VCC:       sample = read_adc_vref();    break;
            case TEMP:      sample = read_adc_temp();    break;
            case JITTER:    sample = read_hsi_per_lsi(); break;
            case FLOAT_PIN: sample = read_adc_float();   break;
        }
        memcpy(dest, &sample, byte_width);
        dest += byte_width;
    }
    return requested*byte_width;
}

void getPrngSeed(uint8_t *dest)
{
    struct __attribute__((packed)) {
        uint16_t vcc[32];
        uint16_t temp[32];
        uint32_t jitter[32];
        uint16_t float_pin[32];
    } s;
    memset(&s, 0, sizeof(s));

    const uint8_t key[16] = SEED_KEY;
    struct AES_CMAC_ctx cmac;
    AES_init_ctx(&s_seed_aes, key);
    AES_CMAC_init_ctx(&cmac, (void *)seed_encrypt);
    entropy_hw_init();

    for(size_t i = 0; i < 2; i++)
    {
        for (int i = 0; i < 32; i++) {
            s.vcc[i]       = read_adc_vref();
            s.temp[i]      = read_adc_temp();
            s.jitter[i]    = read_hsi_per_lsi();
            s.float_pin[i] = read_adc_float();
        }   

        AES_CMAC_digest(&cmac, (uint8_t *)&s, sizeof(s), dest+(i*16));
    }
}