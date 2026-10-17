/* ADC0 and ADC1 register driver (RM chapter 44): calibration at start, then blocking 12-bit conversions with 8-sample hardware
 * averaging. Written from the RM; compiled and linked for the S32K144, NEVER RUN on a part.
 *
 * Clocks: ADCK comes from FIRCDIV2 (48 MHz; the display HAL already enables it) through PCC_ADCn[PCS] = 011. The data sheet's
 * ADCK limits are not in the reference set, so both numbers are deliberately conservative: calibration at 48/8 = 6 MHz (the RM
 * wants half the maximum or less) and conversions at 48/4 = 12 MHz. With the default 13.5-cycle sample time that is about
 * 1.1 us of sampling, ample for the 100 nF filter capacitor that is the actual source. */
#include <stdbool.h>
#include "adc.h"
#include "gauges_pins.h"
#include "s32k144_regs.h"

typedef struct { uint32_t base; uint8_t channel; } adc_pin_t;

static const adc_pin_t ADC_PIN[ADC_CH_COUNT] = {
    { ADC0_BASE, 0 },       /* ADC_CH_FUEL   PIN_ADC_FUEL, ADC0_SE0 */
    { ADC0_BASE, 1 },       /* ADC_CH_OIL    PIN_ADC_OIL,  ADC0_SE1 */
    { ADC1_BASE, 0 },       /* ADC_CH_TEMP   PIN_ADC_TEMP, ADC1_SE0 */
    { ADC1_BASE, 1 },       /* ADC_CH_BATT   PIN_ADC_BATT, ADC1_SE1 */
    { ADC0_BASE, 7 },       /* ADC_CH_DIMMER PIN_DIM_ADC,  ADC0_SE7 */
};

#define PCS_FIRCDIV2 3u
#define POLL_LIMIT   100000u

static bool g_ready;

static void calibrate(uint32_t b)
{
    ADC_CFG1(b) = ADC_CFG1_ADIV(3) | ADC_CFG1_MODE_12;              /* ADCK = 6 MHz, 12-bit, ALTCLK1 */
    ADC_CLPS(b) = 0u; ADC_CLP3(b) = 0u; ADC_CLP2(b) = 0u; ADC_CLP1(b) = 0u; ADC_CLP0(b) = 0u; ADC_CLPX(b) = 0u; ADC_CLP9(b) = 0u;
    ADC_SC3(b) = ADC_SC3_CAL | ADC_SC3_AVGE | ADC_SC3_AVGS(3);      /* the RM requires averaging over 32 for calibration */
    for (uint32_t k = 0; k < POLL_LIMIT * 10u && (ADC_SC3(b) & ADC_SC3_CAL) != 0u; k++) { }
    for (uint32_t k = 0; k < POLL_LIMIT && (ADC_SC1A(b) & ADC_SC1_COCO) == 0u; k++) { }
    (void)ADC_RA(b);                                                /* reading the result clears COCO */
    ADC_CFG1(b) = ADC_CFG1_ADIV(2) | ADC_CFG1_MODE_12;              /* ADCK = 12 MHz for use */
    ADC_SC3(b) = ADC_SC3_AVGE | ADC_SC3_AVGS(1);                    /* 8 conversions averaged, one-shot */
}

void adc_hw_init(void)
{
    /* VREFH is the 3V3 analog supply and must have settled before calibration: main() calls this after the clock is up and the
     * display initialisation (hundreds of milliseconds) has given the rail time. */
    SCG_FIRCDIV = (SCG_FIRCDIV & ~0x700u) | SCG_FIRCDIV2(1);
    PCC_ADC0 = 0u;
    PCC_ADC0 = PCC_PCS(PCS_FIRCDIV2) | PCC_CGC;
    PCC_ADC1 = 0u;
    PCC_ADC1 = PCC_PCS(PCS_FIRCDIV2) | PCC_CGC;
    calibrate(ADC0_BASE);               /* one ADC at a time (RM 44.5.6) */
    calibrate(ADC1_BASE);
    g_ready = true;
}

static uint16_t adc_read(adc_ch_t ch)
{
    if (!g_ready || (unsigned)ch >= ADC_CH_COUNT) return ADC_FAIL;
    uint32_t b = ADC_PIN[ch].base;
    ADC_SC1A(b) = ADC_PIN[ch].channel;                              /* writing SC1A starts a conversion (software trigger) */
    for (uint32_t k = 0; k < POLL_LIMIT; k++)
        if (ADC_SC1A(b) & ADC_SC1_COCO)
            return (uint16_t)(ADC_RA(b) & 0xFFFu);
    return ADC_FAIL;
}

const adc_ops_t adc_s32k = { adc_read };
