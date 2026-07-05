#include <stdint.h>
#include <string.h>
#include <stdbool.h>

#include "inc/hw_memmap.h"
#include "driverlib/gpio.h"
#include "driverlib/sysctl.h"
#include "driverlib/adc.h"

#include "aes_cmac.h"
#include "aes.h"
#include "secrets.h"

/* AIN0 = PE3, AIN1 = PE2 */
#define ENTROPY_GPIO_PORT    GPIO_PORTE_BASE
#define ENTROPY_GPIO_PINS    (GPIO_PIN_3 | GPIO_PIN_2)

void entropy_init(void)
{
    SysCtlPeripheralEnable(SYSCTL_PERIPH_ADC0);
    SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOE);
    while (!SysCtlPeripheralReady(SYSCTL_PERIPH_ADC0));
    while (!SysCtlPeripheralReady(SYSCTL_PERIPH_GPIOE));
    while (!SysCtlPeripheralReady(SYSCTL_PERIPH_GPIOE));

    GPIOPinTypeADC(ENTROPY_GPIO_PORT, ENTROPY_GPIO_PINS);

    ADCSequenceConfigure(ADC0_BASE, 3, ADC_TRIGGER_PROCESSOR, 0);
}

static uint16_t adc_read_step(uint32_t step_config)
{
    uint32_t val;
    ADCSequenceDisable(ADC0_BASE, 3);
    ADCSequenceStepConfigure(ADC0_BASE, 3, 0, step_config);
    ADCSequenceEnable(ADC0_BASE, 3);
    ADCIntClear(ADC0_BASE, 3);
    ADCProcessorTrigger(ADC0_BASE, 3);
    while (!ADCIntStatus(ADC0_BASE, 3, false));
    ADCIntClear(ADC0_BASE, 3);
    ADCSequenceDataGet(ADC0_BASE, 3, &val);
    return (uint16_t)(val & 0xFFFU);
}

uint16_t entropy_adc_temp(void)
{
    //return 0;
    return adc_read_step(ADC_CTL_TS | ADC_CTL_IE | ADC_CTL_END);
}

uint16_t entropy_adc_float(void)
{
    //return 0;
    return adc_read_step(ADC_CTL_CH0 | ADC_CTL_IE | ADC_CTL_END);
}

static struct AES_ctx s_seed_aes;
static void seed_encrypt(uint8_t *data) { AES_ECB_encrypt(&s_seed_aes, data); }

const char * getEntropyDescription(void)
{
    return "{\"temp\":2,\"float_pin\":2}";
}

uint16_t getEntropySamples(uint8_t num_samples, uint8_t* dest)
{
    uint8_t byte_width = 4;

    for( size_t count = 0; count < num_samples; count++ )
    {
        uint16_t sample_16b = entropy_adc_temp();
        memcpy(dest, &sample_16b, 2);

        sample_16b = entropy_adc_float();
        memcpy(dest+2, &sample_16b, 2);
        
        dest += byte_width;
    }
    return num_samples*byte_width;
}

enum { TEMP, FLOAT_PIN, NUM_SOURCES };

uint8_t getEntropySourceCount(void){ return NUM_SOURCES; }

const char * getEntropySourceName(uint8_t source_num)
{
    const static char* names[NUM_SOURCES] = { [TEMP] = "temp",
                                              [FLOAT_PIN] = "float_pin"
                                            };
    return source_num < NUM_SOURCES ? names[source_num] : "Invalid source number";
}

uint16_t getEntropySourceSamples(uint8_t source_num, uint8_t num_samples, uint8_t* dest)
{
    const static uint8_t byte_widths[NUM_SOURCES] = { [TEMP] = 2,
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
            case TEMP:      sample = entropy_adc_temp();    break;
            case FLOAT_PIN: sample = entropy_adc_float();   break;
        }
        memcpy(dest, &sample, byte_width);
        dest += byte_width;
    }
    return requested*byte_width;
}

void getPrngSeed(uint8_t *dest)
{
    struct __attribute__((packed)) {
        uint16_t temp[64];
        uint16_t float_pin[64];
    } s;
    memset(&s, 0, sizeof(s));

    const uint8_t key[16] = SEED_KEY;
    struct AES_CMAC_ctx cmac;
    AES_init_ctx(&s_seed_aes, key);
    AES_CMAC_init_ctx(&cmac, (void *)seed_encrypt);
    entropy_init();

    for(size_t i = 0; i < 2; i++)
    {
        for (int i = 0; i < 64; i++) {
            s.temp[i]      = entropy_adc_temp();
            s.float_pin[i] = entropy_adc_float();
        }   

        AES_CMAC_digest(&cmac, (uint8_t *)&s, sizeof(s), dest+(i*16));
    }
}