#include <stddef.h>
#include "senders.h"

/* Every 10 ms poll reads the three sender channels and the battery, then flips the sender excitation, so a channel gets one
 * reading with the excitation on and one with it off every 20 ms (the 10 ms in between is ample settling: the slowest node is
 * the 1 k / 100 nF filter, 0.1 ms). Each phase keeps its own filtered code; the resistance comes from the two filtered codes
 * (senders.h has the circuit). Filter coefficients are shifts of the 12-bit code scaled by 4096 (so the integer division
 * leaves a dead band of 2^shift / 4096 of a code, not several codes): y += (x*4096 - y) / 2^shift, a time constant of about
 * 2^shift samples, 20 ms each for a sender phase and 10 ms for the battery. A fuel gauge wants heavy damping against slosh;
 * the others follow in a second or so. */
enum { CH_FUEL = 0, CH_OIL, CH_TEMP, CH_SENDERS, CH_BATT = CH_SENDERS };
static const uint8_t SHIFT[CH_SENDERS] = { 8, 5, 6 };      /* ~5.1 s, 0.64 s, 1.3 s */
#define BATT_SHIFT 6u                                         /* ~0.64 s */
static const adc_ch_t ADC_OF[CH_SENDERS] = { ADC_CH_FUEL, ADC_CH_OIL, ADC_CH_TEMP };

typedef struct {
    int32_t  y[2];              /* filtered code x 4096, [0] excitation off, [1] on */
    bool     have[2];
    uint8_t  open_run, short_run, gnd_run, ok_run;
    bool     open, shorted, ground_fault;
    float    ohm, ground;       /* the last solution: sender ohms and its ground offset in VREF units */
    uint16_t off_raw;           /* the last unfiltered code with the excitation off (ground-fault test) */
    bool     solved;
    uint32_t stamp_ms;
} chan_t;

static const adc_ops_t *g_adc;
static const sender_hw_t *g_hw;
static chan_t g_ch[CH_SENDERS];
static int32_t g_batt_y;
static bool g_batt_have;
static uint32_t g_batt_stamp;
static bool g_exc;              /* the excitation state the current poll is reading */
static const sender_pt_t *g_curve[SENDER_COUNT];
static uint8_t g_curve_n[SENDER_COUNT];
static uint32_t g_now;
#define STALE_MS 2000u         /* a channel whose ADC reads have stopped succeeding stops being valid after this */

void senders_init(const adc_ops_t *adc, const sender_hw_t *hw)
{
    g_adc = (hw != NULL) ? adc : NULL;
    g_hw = hw;
    for (unsigned i = 0; i < CH_SENDERS; i++) g_ch[i] = (chan_t){ { 0, 0 }, { false, false }, 0, 0, 0, 0, false, false, false,
                                                                  0.0f, 0.0f, 4095u, false, 0u };
    g_batt_y = 0; g_batt_have = false; g_batt_stamp = 0u;
    g_now = 0u;
    for (unsigned i = 0; i < SENDER_COUNT; i++) { g_curve[i] = NULL; g_curve_n[i] = 0u; }
    g_exc = true;
    if (g_hw != NULL && g_hw->excite != NULL) g_hw->excite(true);
}

void senders_set_curve(sender_kind_t k, const sender_pt_t *pts, uint8_t n)
{
    if ((unsigned)k < SENDER_COUNT) { g_curve[k] = pts; g_curve_n[k] = n; }
}

static void sat_inc(uint8_t *v) { if (*v < 255u) (*v)++; }

static void filt(int32_t *y, bool *have, uint16_t code, uint8_t shift)
{
    int32_t x = (int32_t)code * 4096;
    if (!*have) { *y = x; *have = true; }
    else *y += (x - *y) / (int32_t)(1u << shift);
}

/* Node voltage from an ADC code, both in VREF units (senders.h). */
#define K_SB (SENDER_SERIES_OHM / SENDER_BIAS_OHM)
static float node_v(float code) { float va = code / 4095.0f; return va * (1.0f + K_SB) - K_SB; }
static float bias_i(float code) { return (1.0f - code / 4095.0f) / SENDER_BIAS_OHM; }

/* Solve every channel from its two filtered codes. The off-phase pull-up current needs the floating rail's voltage, the
 * mean of the three node voltages, so all three are solved together. */
static void solve(void)
{
    float vs_off[CH_SENDERS], rail = 0.0f;
    for (unsigned i = 0; i < CH_SENDERS; i++) {
        vs_off[i] = g_ch[i].have[0] ? node_v((float)g_ch[i].y[0] / 4096.0f) : 0.0f;
        rail += vs_off[i];
    }
    rail /= (float)CH_SENDERS;
    for (unsigned i = 0; i < CH_SENDERS; i++) {
        chan_t *c = &g_ch[i];
        c->solved = false;
        if (!c->have[0] || !c->have[1]) continue;
        float code_on = (float)c->y[1] / 4096.0f, code_off = (float)c->y[0] / 4096.0f;
        float vs_on = node_v(code_on);
        float i_on = (1.0f - vs_on) / SENDER_PULLUP_OHM + bias_i(code_on);
        float i_off = (rail - vs_off[i]) / SENDER_PULLUP_OHM + bias_i(code_off);
        float di = i_on - i_off;
        if (di <= 1e-7f) continue;                          /* no excitation reaching the node (an open wire): no solution */
        float r = (vs_on - vs_off[i]) / di;
        if (r < 0.0f) r = 0.0f;
        c->ohm = r;
        c->ground = vs_on - i_on * r;
        c->solved = true;
    }
}

static void flag(chan_t *c, uint16_t code_on_now)
{
    bool open = code_on_now >= SENDER_OPEN_CODE;
    bool gnd = c->have[0] && c->off_raw <= SENDER_GROUND_CODE;     /* unfiltered: an offset that large is not noise */
    bool shorted = !open && !gnd && c->solved && c->ohm < SENDER_SHORT_OHM;
    if (open) { sat_inc(&c->open_run); c->short_run = 0; c->gnd_run = 0; c->ok_run = 0; }
    else if (gnd) { sat_inc(&c->gnd_run); c->open_run = 0; c->short_run = 0; c->ok_run = 0; }
    else if (shorted) { sat_inc(&c->short_run); c->open_run = 0; c->gnd_run = 0; c->ok_run = 0; }
    else { c->open_run = 0; c->short_run = 0; c->gnd_run = 0; sat_inc(&c->ok_run); }
    if (c->open_run >= SENDER_FLAG_SAMPLES) c->open = true;
    if (c->short_run >= SENDER_FLAG_SAMPLES) c->shorted = true;
    if (c->gnd_run >= SENDER_FLAG_SAMPLES) c->ground_fault = true;
    if (c->ok_run >= 5u) { c->open = false; c->shorted = false; c->ground_fault = false; }
}

void senders_poll(uint32_t now_ms)
{
    if (g_adc == NULL) return;
    g_now = now_ms;
    unsigned phase = g_exc ? 1u : 0u;
    uint16_t code_on_now[CH_SENDERS] = { 0, 0, 0 };
    bool got[CH_SENDERS] = { false, false, false };
    for (unsigned i = 0; i < CH_SENDERS; i++) {
        uint16_t code = g_adc->read(ADC_OF[i]);
        if (code == ADC_FAIL || code > 4095u) continue;     /* no reading this time: the old value ages out through its stamp */
        filt(&g_ch[i].y[phase], &g_ch[i].have[phase], code, SHIFT[i]);
        g_ch[i].stamp_ms = now_ms;
        got[i] = true;
        if (phase == 1u) code_on_now[i] = code;
        else g_ch[i].off_raw = code;
    }
    uint16_t b = g_adc->read(ADC_CH_BATT);
    if (b != ADC_FAIL && b <= 4095u) { filt(&g_batt_y, &g_batt_have, b, BATT_SHIFT); g_batt_stamp = now_ms; }
    solve();
    if (phase == 1u)
        for (unsigned i = 0; i < CH_SENDERS; i++)
            if (got[i]) flag(&g_ch[i], code_on_now[i]);
    g_exc = !g_exc;                                         /* the next poll reads the other phase */
    if (g_hw->excite != NULL) g_hw->excite(g_exc);
}

static bool fresh(uint32_t stamp, bool have) { return have && (uint32_t)(g_now - stamp) <= STALE_MS; }
static bool usable(const chan_t *c)
{
    return fresh(c->stamp_ms, c->have[0] && c->have[1]) && c->solved && !c->open && !c->shorted && !c->ground_fault;
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
    if (!usable(c) || g_curve_n[k] < 2u || g_curve[k] == NULL) return s;
    float v = curve_lookup(k, c->ohm);
    s.value = v < lo ? lo : (v > hi ? hi : v);
    s.valid = true;
    return s;
}

sample_t senders_fuel_pct(void) { return sender_value(SENDER_FUEL, CH_FUEL, 0.0f, 100.0f); }
sample_t senders_oil_kpa(void) { return sender_value(SENDER_OIL, CH_OIL, 0.0f, 1000.0f); }
sample_t senders_coolant_c(void) { return sender_value(SENDER_COOLANT, CH_TEMP, -40.0f, 200.0f); }

sample_t senders_battery_v(void)
{
    sample_t s = { 0.0f, false, g_batt_stamp };
    if (!fresh(g_batt_stamp, g_batt_have)) return s;
    s.value = (float)g_batt_y / 4096.0f / 4095.0f * SENDER_VREF_V * BATT_DIVIDER;
    s.valid = true;
    return s;
}

/* A ground fault is reported in the open mask too: either way the wire does not give a reading, and the existing CAN
 * message (and the dash) have room for one "no reading" bit per sender. */
uint8_t senders_open_mask(void)
{
    uint8_t m = 0u;
    for (unsigned i = 0; i < CH_SENDERS; i++)
        if (g_ch[i].open || g_ch[i].ground_fault) m |= (uint8_t)(1u << i);
    return m;
}

uint8_t senders_short_mask(void)
{
    uint8_t m = 0u;
    for (unsigned i = 0; i < CH_SENDERS; i++)
        if (g_ch[i].shorted) m |= (uint8_t)(1u << i);
    return m;
}

uint8_t senders_ground_fault_mask(void)
{
    uint8_t m = 0u;
    for (unsigned i = 0; i < CH_SENDERS; i++)
        if (g_ch[i].ground_fault) m |= (uint8_t)(1u << i);
    return m;
}

float senders_ohms(sender_kind_t k)
{
    if ((unsigned)k >= SENDER_COUNT) return -1.0f;
    const chan_t *c = &g_ch[k];                      /* SENDER_FUEL/OIL/COOLANT are channels 0/1/2 */
    if (!c->solved || c->open || c->shorted || c->ground_fault) return -1.0f;
    return c->ohm;
}

float senders_ground_mv(sender_kind_t k)
{
    if ((unsigned)k >= SENDER_COUNT || !g_ch[k].solved) return 0.0f;
    return g_ch[k].ground * SENDER_VREF_V * 1000.0f;
}
