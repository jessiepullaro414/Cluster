#include <stddef.h>
#include "capture.h"
#include "inputmath.h"
#include "inputs.h"

#define DIMMER_PERIOD_MS 100u
#define VREF_MV          3300u      /* VREFH is tied to the filtered 3V3 analog supply on gauges/ */
#define IGN_DEBOUNCE_MS  50u

static const inputs_hw_t *g_hw;
static const adc_ops_t *g_adc;

static capture_t g_cap[2];          /* written by the capture interrupt, read under irq_lock */
static uint32_t g_ppm = 16000u;
static uint8_t g_tach_ppr = 4u;

static sample_t g_speed, g_tach;
static lamp_debounce_t g_lamp[LAMP_COUNT];
static lamp_debounce_t g_ign;
static uint32_t g_last_poll_ms;
static bool g_first;
static uint32_t g_dim_next_ms;
static bool g_dim_on;
static uint8_t g_dim_pct = 100u;
static uint8_t g_ign_hold;          /* ignition debounce uses 50 ms; im_lamp_update debounces 20 ms, so count in steps */
static bool g_ign_state;

void inputs_init(const inputs_hw_t *hw, const adc_ops_t *adc)
{
    g_hw = hw; g_adc = adc;
    capture_reset(&g_cap[0]); capture_reset(&g_cap[1]);
    g_speed = (sample_t){ 0.0f, false, 0u };
    g_tach = (sample_t){ 0.0f, false, 0u };
    for (unsigned i = 0; i < LAMP_COUNT; i++) g_lamp[i] = (lamp_debounce_t){ false, false, 0u };
    g_ign = (lamp_debounce_t){ false, false, 0u };
    g_first = true; g_dim_next_ms = 0u; g_dim_on = false; g_dim_pct = 100u; g_ign_hold = 0u; g_ign_state = false;
}

void inputs_configure(uint32_t pulses_per_mile, uint8_t tach_pulses_per_rev)
{
    if (pulses_per_mile != 0u) g_ppm = pulses_per_mile;
    if (tach_pulses_per_rev != 0u) g_tach_ppr = tach_pulses_per_rev;
}

/* Interrupt context. */
void inputs_on_capture(unsigned channel, uint32_t t_us)
{
    if (channel < 2u) capture_edge(&g_cap[channel], t_us);
}

static capture_t snapshot(unsigned ch, uint32_t now_us)
{
    capture_t c;
    if (g_hw->irq_lock) g_hw->irq_lock();
    capture_keepalive(&g_cap[ch], now_us);
    c = g_cap[ch];
    if (g_hw->irq_unlock) g_hw->irq_unlock();
    return c;
}

static sample_t from_capture(unsigned ch, uint32_t now_us, uint32_t now_ms, bool is_tach)
{
    sample_t s = { 0.0f, false, now_ms };
    capture_t c = snapshot(ch, now_us);
    uint32_t period;
    switch (capture_state(&c, now_us, &period)) {
    case CAP_RUNNING:
        s.valid = true;
        s.value = is_tach ? im_rpm(period, g_tach_ppr) : im_speed_kph(period, g_ppm);
        break;
    case CAP_STOPPED:
        s.valid = true;                              /* a sender that is there and not pulsing: standing still */
        s.value = 0.0f;
        break;
    case CAP_ABSENT:
    case CAP_FAULT:
        break;
    }
    return s;
}

void inputs_poll(uint32_t now_ms)
{
    if (g_hw == NULL) return;
    uint32_t elapsed = g_first ? 10u : now_ms - g_last_poll_ms;
    if (elapsed > 255u) elapsed = 255u;
    g_first = false;
    g_last_poll_ms = now_ms;

    uint32_t now_us = g_hw->now_us();
    g_speed = from_capture(0, now_us, now_ms, false);
    g_tach = from_capture(1, now_us, now_ms, true);

    uint8_t raw = g_hw->lamps_raw();
    for (unsigned i = 0; i < LAMP_COUNT; i++)
        (void)im_lamp_update(&g_lamp[i], ((raw >> i) & 1u) != 0u, (uint8_t)elapsed);

    /* ignition: a longer debounce than the lamps (switch bounce, cranking dips); im_lamp_update's 20 ms is the first stage */
    bool ign = im_lamp_update(&g_ign, g_hw->ign_raw(), (uint8_t)elapsed);
    if (ign == g_ign_state) g_ign_hold = 0u;
    else {
        unsigned h = g_ign_hold + elapsed;
        g_ign_hold = (uint8_t)(h > 255u ? 255u : h);
        if (g_ign_hold >= IGN_DEBOUNCE_MS - IM_LAMP_DEBOUNCE_MS) { g_ign_state = ign; g_ign_hold = 0u; }
    }

    if (g_adc != NULL && (int32_t)(now_ms - g_dim_next_ms) >= 0) {
        g_dim_next_ms = now_ms + DIMMER_PERIOD_MS;
        uint16_t a = g_adc->read(ADC_CH_DIMMER);
        if (a != ADC_FAIL) {
            g_dim_on = im_dim_lights_on(a, VREF_MV);
            g_dim_pct = im_dim_percent(a, VREF_MV);
        }
    }
}

sample_t inputs_speed_kph(void) { return g_speed; }
sample_t inputs_rpm_from_tach(void) { return g_tach; }

lamps_t inputs_lamps(uint8_t invert_mask)
{
    bool v[LAMP_COUNT];
    for (unsigned i = 0; i < LAMP_COUNT; i++)
        v[i] = g_lamp[i].state != (((invert_mask >> i) & 1u) != 0u);       /* active-low lamps are on when the pin is low */
    lamps_t l = { v[0], v[1], v[2], v[3], v[4], v[5] };
    return l;
}

bool inputs_dash_lights_on(void) { return g_dim_on; }
uint8_t inputs_dimmer_pct(void) { return g_dim_pct; }
bool inputs_ignition_on(void) { return g_ign_state; }
