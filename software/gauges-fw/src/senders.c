#include <stddef.h>
#include "senders.h"

/* One channel per 10 ms poll, so each is read every 40 ms (four channels). Filter coefficients are shifts of the 12-bit code
 * scaled by 4096 (so the integer division leaves a dead band of 2^shift / 4096 of a code, not several codes): y += (x*4096 - y) / 2^shift,
 * a time constant of about 2^shift samples = 2^shift * 40 ms. A fuel gauge wants
 * heavy damping against slosh; the others follow in a second or so. */
enum { CH_FUEL = 0, CH_OIL, CH_TEMP, CH_BATT, CH_COUNT };
static const uint8_t SHIFT[CH_COUNT] = { 7, 4, 5, 4 };     /* ~5.1 s, 0.64 s, 1.3 s, 0.64 s */
static const adc_ch_t ADC_OF[CH_COUNT] = { ADC_CH_FUEL, ADC_CH_OIL, ADC_CH_TEMP, ADC_CH_BATT };

typedef struct {
    int32_t  y;                 /* filtered code x 4096 */
    bool     have;
    uint8_t  open_run, short_run, ok_run;
    bool     open, shorted;
    uint32_t stamp_ms;
} chan_t;

static const adc_ops_t *g_adc;
static chan_t g_ch[CH_COUNT];
static const sender_pt_t *g_curve[SENDER_COUNT];
static uint8_t g_curve_n[SENDER_COUNT];
static uint8_t g_next;
static uint32_t g_now;
#define STALE_MS 2000u         /* a channel whose ADC reads have stopped succeeding stops being valid after this */

void senders_init(const adc_ops_t *adc)
{
    g_adc = adc;
    for (unsigned i = 0; i < CH_COUNT; i++) g_ch[i] = (chan_t){ 0, false, 0, 0, 0, false, false, 0u };
    g_now = 0u;
    for (unsigned i = 0; i < SENDER_COUNT; i++) { g_curve[i] = NULL; g_curve_n[i] = 0u; }
    g_next = 0u;
}

void senders_set_curve(sender_kind_t k, const sender_pt_t *pts, uint8_t n)
{
    if ((unsigned)k < SENDER_COUNT) { g_curve[k] = pts; g_curve_n[k] = n; }
}

static void sat_inc(uint8_t *v) { if (*v < 255u) (*v)++; }

static void take(unsigned i, uint32_t now_ms)
{
    chan_t *c = &g_ch[i];
    uint16_t code = g_adc->read(ADC_OF[i]);
    if (code == ADC_FAIL || code > 4095u) return;               /* no reading this time: the old value ages out through its stamp */
    c->stamp_ms = now_ms;
    bool is_sender = i != CH_BATT;
    if (is_sender) {
        if (code >= SENDER_OPEN_CODE) { sat_inc(&c->open_run); c->short_run = 0; c->ok_run = 0; }
        else if (code <= SENDER_SHORT_CODE) { sat_inc(&c->short_run); c->open_run = 0; c->ok_run = 0; }
        else { c->open_run = 0; c->short_run = 0; sat_inc(&c->ok_run); }
        if (c->open_run >= SENDER_FLAG_SAMPLES) c->open = true;
        if (c->short_run >= SENDER_FLAG_SAMPLES) c->shorted = true;
        if (c->ok_run >= 5u) { c->open = false; c->shorted = false; }
    }
    int32_t x = (int32_t)code * 4096;
    if (!c->have) { c->y = x; c->have = true; }
    else c->y += (x - c->y) / (int32_t)(1u << SHIFT[i]);
}

void senders_poll(uint32_t now_ms)
{
    if (g_adc == NULL) return;
    g_now = now_ms;
    take(g_next, now_ms);
    g_next = (uint8_t)((g_next + 1u) % CH_COUNT);
}

static float code_of(const chan_t *c) { return (float)c->y / 4096.0f; }
static bool fresh(const chan_t *c) { return c->have && (uint32_t)(g_now - c->stamp_ms) <= STALE_MS; }

static float ohms_of(const chan_t *c)
{
    float code = code_of(c);
    if (code > 4094.5f) code = 4094.5f;
    return SENDER_PULLUP_OHM * code / (4095.0f - code);
}

static float curve_lookup(sender_kind_t k, float ohm)
{
    const sender_pt_t *p = g_curve[k];
    uint8_t n = g_curve_n[k];
    if (ohm <= p[0].ohm) return p[0].value;
    for (uint8_t i = 1; i < n; i++) {
        if (ohm <= p[i].ohm) {
            float t = (ohm - p[i - 1].ohm) / (p[i].ohm - p[i - 1].ohm);
            return p[i - 1].value + t * (p[i].value - p[i - 1].value);
        }
    }
    return p[n - 1].value;
}

static sample_t sender_value(sender_kind_t k, unsigned ch, float lo, float hi)
{
    sample_t s = { 0.0f, false, g_ch[ch].stamp_ms };
    const chan_t *c = &g_ch[ch];
    if (!fresh(c) || c->open || c->shorted || g_curve_n[k] < 2u || g_curve[k] == NULL) return s;
    float v = curve_lookup(k, ohms_of(c));
    s.value = v < lo ? lo : (v > hi ? hi : v);
    s.valid = true;
    return s;
}

sample_t senders_fuel_pct(void) { return sender_value(SENDER_FUEL, CH_FUEL, 0.0f, 100.0f); }
sample_t senders_oil_kpa(void) { return sender_value(SENDER_OIL, CH_OIL, 0.0f, 1000.0f); }
sample_t senders_coolant_c(void) { return sender_value(SENDER_COOLANT, CH_TEMP, -40.0f, 200.0f); }

sample_t senders_battery_v(void)
{
    sample_t s = { 0.0f, false, g_ch[CH_BATT].stamp_ms };
    if (!fresh(&g_ch[CH_BATT])) return s;
    s.value = code_of(&g_ch[CH_BATT]) / 4095.0f * SENDER_VREF_V * BATT_DIVIDER;
    s.valid = true;
    return s;
}

uint8_t senders_open_mask(void)
{
    return (uint8_t)((g_ch[CH_FUEL].open ? 1u : 0u) | (g_ch[CH_OIL].open ? 2u : 0u) | (g_ch[CH_TEMP].open ? 4u : 0u));
}

uint8_t senders_short_mask(void)
{
    return (uint8_t)((g_ch[CH_FUEL].shorted ? 1u : 0u) | (g_ch[CH_OIL].shorted ? 2u : 0u) | (g_ch[CH_TEMP].shorted ? 4u : 0u));
}

float senders_ohms(sender_kind_t k)
{
    static const uint8_t CH_OF[SENDER_COUNT] = { CH_FUEL, CH_OIL, CH_TEMP };
    if ((unsigned)k >= SENDER_COUNT) return -1.0f;
    const chan_t *c = &g_ch[CH_OF[k]];
    if (!c->have || c->open || c->shorted) return -1.0f;
    return ohms_of(c);
}
