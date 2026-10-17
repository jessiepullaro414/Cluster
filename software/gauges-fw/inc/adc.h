#ifndef ADC_H
#define ADC_H
/* The 12-bit ADC behind a function so senders.c and the dimmer input run on the host against a fake and on the part against
 * the register driver (adc_s32k.c). Reads are blocking (hardware-averaged, tens of microseconds). */
#include <stdint.h>

typedef enum {
    ADC_CH_FUEL = 0,        /* ADC0_SE0, PTA0 */
    ADC_CH_OIL,             /* ADC0_SE1, PTA1 */
    ADC_CH_TEMP,            /* ADC1_SE0, PTA2 */
    ADC_CH_BATT,            /* ADC1_SE1, PTA3 */
    ADC_CH_DIMMER,          /* ADC0_SE7, PTB3 */
    ADC_CH_COUNT
} adc_ch_t;

#define ADC_FAIL 0xFFFFu    /* the conversion did not finish */

typedef struct {
    uint16_t (*read)(adc_ch_t ch);      /* 0..4095 as a fraction of VREFH (= the 3.3 V analog supply), or ADC_FAIL */
} adc_ops_t;

extern const adc_ops_t adc_s32k;
void adc_hw_init(void);      /* clocks and calibration; call once the 3V3 analog rail has settled */

#endif
