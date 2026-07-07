#include <stdint.h>
#include <string.h>
#include <stdbool.h>

#include "inc/hw_memmap.h"
#include "inc/hw_types.h"
#include "inc/hw_sysctl.h"
#include "inc/hw_adc.h"
#include "driverlib/gpio.h"
#include "driverlib/sysctl.h"
#include "driverlib/adc.h"

#include "aes_cmac.h"
#include "aes.h"
#include "secrets.h"
#include "uart.h"

/* AIN0 = PE3, AIN1 = PE2 */
#define ENTROPY_GPIO_PORT    GPIO_PORTE_BASE
#define ENTROPY_GPIO_PINS    (GPIO_PIN_3 | GPIO_PIN_2)

/* Bound on how many times the entropy init/read busy-waits poll their
 * respective ready/status bits before giving up. Ample margin over a
 * normal conversion or clock-gating settle (at most a handful of bus
 * cycles), but finite -- so a stuck peripheral after a warm
 * SysCtlReset() reboot dumps diagnostics instead of hanging the boot
 * banner forever. */
#define PERIPH_WAIT_MAX_ITERS 100000u

static void uart_write_str(const char *s)
{
    uart_write(HOST_UART, (uint8_t *)s, strlen(s));
}

static void uart_write_hex_u32(uint32_t val)
{
    static const char hexdigits[] = "0123456789ABCDEF";
    char buf[8];
    for (int i = 0; i < 8; i++)
    {
        buf[i] = hexdigits[(val >> ((7 - i) * 4)) & 0xF];
    }
    uart_write(HOST_UART, (uint8_t *)buf, 8);
}

static void entropy_dump_timeout_diagnostics(const char *stage)
{
    uart_write_str("ENTROPY_TIMEOUT stage=");
    uart_write_str(stage);
    uart_write_str(" RCGCADC=");
    uart_write_hex_u32(HWREG(SYSCTL_RCGCADC));
    uart_write_str(" PRADC=");
    uart_write_hex_u32(HWREG(SYSCTL_PRADC));
    uart_write_str(" RCGCGPIO=");
    uart_write_hex_u32(HWREG(SYSCTL_RCGCGPIO));
    uart_write_str(" PRGPIO=");
    uart_write_hex_u32(HWREG(SYSCTL_PRGPIO));
    uart_write_str(" ACTSS=");
    uart_write_hex_u32(HWREG(ADC0_BASE + ADC_O_ACTSS));
    uart_write_str(" EMUX=");
    uart_write_hex_u32(HWREG(ADC0_BASE + ADC_O_EMUX));
    uart_write_str(" PSSI=");
    uart_write_hex_u32(HWREG(ADC0_BASE + ADC_O_PSSI));
    uart_write_str(" RIS=");
    uart_write_hex_u32(HWREG(ADC0_BASE + ADC_O_RIS));
    uart_write_str(" ISC=");
    uart_write_hex_u32(HWREG(ADC0_BASE + ADC_O_ISC));
    uart_write_str(" OSTAT=");
    uart_write_hex_u32(HWREG(ADC0_BASE + ADC_O_OSTAT));
    uart_write_str("\n");
}

static bool wait_peripheral_ready(uint32_t peripheral)
{
    uint32_t spins;
    for (spins = 0; spins < PERIPH_WAIT_MAX_ITERS && !SysCtlPeripheralReady(peripheral); spins++);
    return spins < PERIPH_WAIT_MAX_ITERS;
}

void entropy_init(void)
{
    SysCtlPeripheralEnable(SYSCTL_PERIPH_ADC0);
    SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOE);
    /* SysCtlPeripheralEnable() is a no-op if the clock was already on, which
     * it is across a warm SysCtlReset() -- unlike a true power-on reset, that
     * doesn't reset ADC0's internal sequencer state machine, so a conversion
     * left in-flight before the reboot can wedge every subsequent read
     * (ACTSS reads back enabled, but RIS never sets). Force a real reset of
     * the module's internal logic. */
    SysCtlPeripheralReset(SYSCTL_PERIPH_ADC0);

    if (!wait_peripheral_ready(SYSCTL_PERIPH_ADC0))
        entropy_dump_timeout_diagnostics("adc0_ready");
    if (!wait_peripheral_ready(SYSCTL_PERIPH_GPIOE))
        entropy_dump_timeout_diagnostics("gpioe_ready");

    GPIOPinTypeADC(ENTROPY_GPIO_PORT, ENTROPY_GPIO_PINS);

    ADCSequenceConfigure(ADC0_BASE, 3, ADC_TRIGGER_PROCESSOR, 0);
}

static uint16_t adc_read_step(uint32_t step_config)
{
    uart_write_str("Inside adc_read_step\n");
    entropy_dump_timeout_diagnostics("adc_read_step");
    uint32_t val;
    ADCSequenceDisable(ADC0_BASE, 3);
    ADCSequenceStepConfigure(ADC0_BASE, 3, 0, step_config);
    ADCSequenceEnable(ADC0_BASE, 3);
    ADCIntClear(ADC0_BASE, 3);
    ADCProcessorTrigger(ADC0_BASE, 3);

    uint32_t spins;
    for (spins = 0; spins < PERIPH_WAIT_MAX_ITERS && !ADCIntStatus(ADC0_BASE, 3, false); spins++);
    if (spins == PERIPH_WAIT_MAX_ITERS)
        entropy_dump_timeout_diagnostics("adc_read_step");

    ADCIntClear(ADC0_BASE, 3);
    ADCSequenceDataGet(ADC0_BASE, 3, &val);
    return (uint16_t)(val & 0xFFFU);
}

uint16_t entropy_adc_temp(void)
{
    return adc_read_step(ADC_CTL_TS | ADC_CTL_IE | ADC_CTL_END);
}

uint16_t entropy_adc_float(void)
{
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
            //s.float_pin[i] = entropy_adc_float();
        }   

        AES_CMAC_digest(&cmac, (uint8_t *)&s, sizeof(s), dest+(i*16));
    }
}