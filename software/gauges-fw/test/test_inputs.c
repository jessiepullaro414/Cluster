/* Capture, inputs and senders against fake hardware: pulse trains with 16-bit timer wraps, stopped and absent senders, glitches,
 * lamp debounce and inversion, ignition, the dimmer against a model of its circuit, ADC readings with open and shorted wires. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "capture.h"
#include "inputmath.h"
#include "inputs.h"
#include "senders.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)
#define NEAR(a, b, tol) do { double _a = (a), _b = (b); if (fabs(_a - _b) > (tol)) { printf("FAIL %s:%d  %s = %g, want %g +- %g\n", __FILE__, __LINE__, #a, _a, _b, (double)(tol)); failures++; } } while (0)

/* ---- the fake hardware -------------------------------------------------------------------------------------- */
static uint32_t fake_us;
static uint8_t fake_lamps;
static bool fake_ign;
static unsigned locks, unlocks;
static uint16_t fake_adc[ADC_CH_COUNT];
static uint16_t adc_fail_mask;
static uint32_t f_now(void) { return fake_us; }
static uint8_t f_lamps(void) { return fake_lamps; }
static bool f_ign(void) { return fake_ign; }
static void f_lock(void) { locks++; }
static void f_unlock(void) { unlocks++; }
/* review 2026-11-03: the three sender channels can come from a model of the real front end instead of fixed codes */
static bool sender_model;
static uint16_t model_code(adc_ch_t ch);
/* 2026-11-04: the dash dimmer against a model of its circuit: the battery, the rheostat, any bulbs left on the feed, and the test load */
static bool dim_model;
static double m_batt, m_rheo, m_bulb, m_drop;   /* m_bulb 0: none */
static bool m_lights, m_load;
static unsigned m_pulses;
static int m_noise;                             /* +- this many ADC counts on every reading */
static unsigned m_seed = 12345u;
static void f_dim_load(bool on) { if (on && !m_load) m_pulses++; m_load = on; }
static uint16_t dim_code(adc_ch_t ch)
{
    double v;
    if (ch == ADC_CH_BATT) v = m_batt / BATT_DIVIDER;
    else {
        double g = 1.0 / m_rheo, i = m_batt / m_rheo;
        if (m_bulb > 0.0) g += 1.0 / m_bulb;
        double feed = i / g;
        if (m_load && feed > m_drop) feed = (i + m_drop / IM_DIM_LOAD_OHM) / (g + 1.0 / IM_DIM_LOAD_OHM);
        v = m_lights ? feed * IM_DIM_DIVIDER : 0.0;
    }
    double code = v / 3.3 * 4095.0 + 0.5;
    if (m_noise) {
        m_seed = m_seed * 1664525u + 1013904223u;
        code += (int)((m_seed >> 16) % (unsigned)(2 * m_noise + 1)) - m_noise;
    }
    return code < 0.0 ? 0u : (code > 4095.0 ? 4095u : (uint16_t)code);
}
static uint16_t f_adc(adc_ch_t ch)
{
    if (adc_fail_mask & (1u << ch)) return ADC_FAIL;
    if (sender_model && ch <= ADC_CH_TEMP) return model_code(ch);
    if (dim_model && (ch == ADC_CH_DIMMER || ch == ADC_CH_BATT)) return dim_code(ch);
    return fake_adc[ch];
}
static const inputs_hw_t HW = { f_now, f_lamps, f_ign, f_lock, f_unlock, f_dim_load };
static const adc_ops_t ADC = { f_adc };

/* ---- capture.c ---------------------------------------------------------------------------------------------- */
static void test_capture_extend(void)
{
    /* the timer wraps every 65536 us; an overflow interrupt that has not run yet must not lose a whole turn */
    CHECK(capture_extend(0, false, 100) == 100u);
    CHECK(capture_extend(3, false, 0xFFF0) == (3u << 16 | 0xFFF0u));
    CHECK(capture_extend(3, true, 0x0010) == (4u << 16 | 0x0010u));          /* captured after the wrap, interrupt pending */
    CHECK(capture_extend(3, true, 0xFFF0) == (3u << 16 | 0xFFF0u));          /* captured just before it */
    CHECK(capture_extend(0xFFFF, true, 0x0001) == 0x00000001u);              /* the 32-bit time itself wraps */
    /* a long run of captures with a counter that wraps at random moments reproduces the true times, including the times when
     * the overflow interrupt has not run yet (a wrap a few microseconds ago) */
    uint32_t true_t = 0xFFFF0000u;
    uint16_t ovf = (uint16_t)(true_t >> 16);
    unsigned seed = 7, late_cases = 0;
    for (int i = 0; i < 200000; i++) {
        seed = seed * 1664525u + 1013904223u;
        true_t += 1000u + (seed >> 20);                                     /* 1.0 .. 5.1 ms apart */
        if (((seed >> 3) & 63u) == 0u) true_t += 20000u + ((seed >> 9) & 0x7FFFu);      /* and now and then a 20 .. 52 ms gap */
        uint16_t cnv = (uint16_t)true_t, wraps = (uint16_t)(true_t >> 16);
        bool late = wraps != ovf && cnv < 0x8000u && ((seed >> 8) & 3u) == 0u;   /* a wrap since the last capture, not yet counted */
        late_cases += late;
        uint32_t t = capture_extend(late ? ovf : wraps, late, cnv);
        if (t != true_t) { CHECK(t == true_t); break; }
        ovf = wraps;                                                        /* the interrupt catches up */
    }
    CHECK(late_cases > 100u);
}

static void test_capture_states(void)
{
    capture_t c; uint32_t p;
    capture_reset(&c);
    CHECK(capture_state(&c, 1000, &p) == CAP_ABSENT);
    capture_edge(&c, 5000);
    CHECK(capture_state(&c, 6000, &p) == CAP_ABSENT);                       /* one edge is not a period */
    capture_edge(&c, 9000);
    CHECK(capture_state(&c, 9500, &p) == CAP_RUNNING && p == 4000u);
    CHECK(capture_state(&c, 12999, &p) == CAP_RUNNING && p == 4000u);       /* not late yet */
    CHECK(capture_state(&c, 13000 + 2000, &p) == CAP_RUNNING && p == 6000u);   /* late: the reading falls */
    CHECK(capture_state(&c, 9000 + 600000, &p) == CAP_STOPPED && p == 0u);
    capture_edge(&c, 9000 + 600000);
    CHECK(capture_state(&c, 9000 + 600100, &p) == CAP_STOPPED);               /* a 600 ms period is still standing still */
    capture_edge(&c, 9000 + 900000);
    CHECK(capture_state(&c, 9000 + 900100, &p) == CAP_RUNNING && p == 300000u);
    /* glitches */
    capture_reset(&c);
    capture_edge(&c, 1000); capture_edge(&c, 5000);
    capture_edge(&c, 5050);                                                 /* 50 us after: bounce */
    capture_edge(&c, 5099);
    CHECK(c.glitches == 2u && c.period_us == 4000u && c.last_us == 5000u);
    capture_edge(&c, 9000);
    CHECK(c.period_us == 4000u);                                            /* the glitches did not disturb the next period */
    /* review 2026-11-03: a points coil rings after each spark; with the tach wire on its negative terminal that puts extra
     * edges 3 and 6 ms after each real one (here at 50 Hz). Blanking half the last period locks onto the real 20 ms within
     * two sparks and then rejects the ringing every time. */
    capture_reset(&c);
    for (uint32_t k = 0; k < 20; k++) {
        uint32_t t = 100000u + k * 20000u;
        capture_edge(&c, t); capture_edge(&c, t + 3000u); capture_edge(&c, t + 6000u);
    }
    CHECK(c.period_us == 20000u && c.glitches >= 36u);
    /* blanking does not hold back a real acceleration: 10 % faster each pulse is accepted */
    capture_reset(&c);
    uint32_t t = 1000u, per = 20000u;
    for (int k = 0; k < 15; k++) { capture_edge(&c, t); t += per; per = per * 9u / 10u; }
    CHECK(c.glitches == 0u && c.period_us < 6000u);
    /* faster than 2 kHz is not a sender */
    capture_reset(&c);
    capture_edge(&c, 1000); capture_edge(&c, 1300);
    CHECK(capture_state(&c, 1301, &p) == CAP_FAULT);
    /* time wrap */
    capture_reset(&c);
    capture_edge(&c, 0xFFFFF000u); capture_edge(&c, 0x00000F00u);           /* 3840 us across the 32-bit wrap */
    CHECK(capture_state(&c, 0x00001000u, &p) == CAP_RUNNING && p == 0x1F00u);
    /* stopped for over an hour must not look recent again after the clock wraps */
    capture_reset(&c);
    capture_edge(&c, 1000); capture_edge(&c, 5000);
    uint32_t now = 5000;
    for (int i = 0; i < 100; i++) {
        now += 100000000u;                                                  /* 100 s per step, 10000 s in all */
        capture_keepalive(&c, now);
        CHECK(capture_state(&c, now, &p) == CAP_STOPPED);
    }
}

/* ---- inputs.c ----------------------------------------------------------------------------------------------- */
static uint32_t ms;
static void run(uint32_t n_ms)
{
    for (uint32_t i = 0; i < n_ms; i += 10) {
        ms += 10u;
        fake_us += 10000u;
        inputs_poll(ms);
    }
}

static void begin(void)
{
    memset(fake_adc, 0, sizeof fake_adc);
    adc_fail_mask = 0; fake_lamps = 0; fake_ign = false; fake_us = 1000000u; ms = 100000u;
    inputs_init(&HW, &ADC);
    inputs_configure(16000u, 4u);
}

/* a pulse train at `hz` for `seconds`, the way the timer interrupt would deliver it */
static void pulses(unsigned ch, double hz, double seconds)
{
    double period = 1.0e6 / hz;
    double next = fake_us + period;
    uint32_t end = fake_us + (uint32_t)(seconds * 1.0e6);
    while (fake_us < end) {
        if (fake_us + 10000u >= (uint32_t)next) {
            while (next <= fake_us + 10000u) { inputs_on_capture(ch, (uint32_t)next); next += period; }
        }
        ms += 10u; fake_us += 10000u;
        inputs_poll(ms);
    }
}

static void test_speed(void)
{
    begin();
    run(100);
    CHECK(!inputs_speed_kph().valid && !inputs_rpm_from_tach().valid);       /* nothing wired: invalid, not zero */
    /* 60 mph = 96.56 km/h at 16000 pulses/mile is 266.67 Hz */
    pulses(0, 266.667, 1.0);
    sample_t s = inputs_speed_kph();
    CHECK(s.valid);
    NEAR(s.value, 96.56, 0.2);
    CHECK(s.stamp_ms == ms);
    /* and a slower one, 5 Hz = 1.8 km/h * ... */
    pulses(0, 5.0, 3.0);
    s = inputs_speed_kph();
    NEAR(s.value, im_speed_kph(200000u, 16000u), 0.01);
    CHECK(s.valid);
    /* the pulses stop: the reading falls as the next pulse is late, then reads a valid zero */
    run(600);
    s = inputs_speed_kph();
    CHECK(s.valid && s.value == 0.0f);
    /* recalibrated at run time */
    inputs_configure(8000u, 4u);
    pulses(0, 266.667, 1.0);
    NEAR(inputs_speed_kph().value, 193.1, 0.5);
    CHECK(locks > 0 && locks == unlocks);                                    /* every lock was released */
    /* noise faster than 2 kHz is not a speed */
    begin();
    pulses(0, 4000.0, 0.3);
    CHECK(!inputs_speed_kph().valid);
}

/* The two-wire VR input (J12, U13): channel 2, the same logic as the Hall input, and nothing to set to choose between them. */
static void test_vr_speed(void)
{
    begin();
    inputs_configure(8000u, 4u);                                             /* a Ford VSS: 8000 pulses per mile */
    run(100);
    CHECK(!inputs_speed_kph().valid);                                        /* neither sensor: invalid, so the car bus can take over */
    /* 60 mph at 8000 pulses/mile is 133.33 Hz */
    pulses(2, 133.333, 1.0);
    sample_t s = inputs_speed_kph();
    CHECK(s.valid);
    NEAR(s.value, 96.56, 0.2);
    CHECK(s.stamp_ms == ms);
    CHECK(!inputs_rpm_from_tach().valid);                                    /* it does not leak into the tach */
    /* standing still: a valid zero, as for a Hall sender */
    run(600);
    s = inputs_speed_kph();
    CHECK(s.valid && s.value == 0.0f);
    /* a walking-pace crawl: 3 mph is 6.7 Hz */
    pulses(2, 6.667, 3.0);
    NEAR(inputs_speed_kph().value, 3.0 * 1.609344, 0.05);
    /* noise faster than 2 kHz is not a speed */
    begin();
    pulses(2, 4000.0, 0.3);
    CHECK(!inputs_speed_kph().valid);

    /* a stray pair of edges on the unused Hall input makes it look like a sensor standing still: it must not pin a moving car to 0 */
    begin();
    inputs_configure(8000u, 4u);
    inputs_on_capture(0, fake_us); inputs_on_capture(0, fake_us + 5000u);
    run(1000);
    CHECK(inputs_speed_kph().valid && inputs_speed_kph().value == 0.0f);      /* standing, as far as anyone can tell */
    pulses(2, 133.333, 1.0);
    NEAR(inputs_speed_kph().value, 96.56, 0.2);
    /* and the same the other way round: a Hall car with a stray pair on the VR input */
    begin();
    inputs_on_capture(2, fake_us); inputs_on_capture(2, fake_us + 5000u);
    run(1000);
    pulses(0, 266.667, 1.0);
    NEAR(inputs_speed_kph().value, 96.56, 0.2);
    /* it stops: both inputs read a standing car, a valid zero */
    run(600);
    s = inputs_speed_kph();
    CHECK(s.valid && s.value == 0.0f);
    /* a channel number from nowhere is ignored */
    begin();
    inputs_on_capture(3, 1000u); inputs_on_capture(3, 2000u); inputs_on_capture(99, 3000u);
    run(100);
    CHECK(!inputs_speed_kph().valid && !inputs_rpm_from_tach().valid);
}

static void test_tach(void)
{
    begin();
    pulses(1, 200.0, 0.5);                                                   /* 4 pulses per rev: 200 Hz is 3000 rpm */
    sample_t t = inputs_rpm_from_tach();
    CHECK(t.valid);
    NEAR(t.value, 3000.0, 1.0);
    inputs_configure(16000u, 8u);
    run(20);
    pulses(1, 200.0, 0.2);
    NEAR(inputs_rpm_from_tach().value, 1500.0, 1.0);
    run(1000);
    CHECK(inputs_rpm_from_tach().valid && inputs_rpm_from_tach().value == 0.0f);   /* engine stopped */
}

static void test_lamps(void)
{
    begin();
    run(50);
    lamps_t l = inputs_lamps(0);
    CHECK(!l.turn_left && !l.turn_right && !l.high_beam && !l.brake && !l.alternator && !l.oil);
    fake_lamps = 0x01u;                          /* turn L pin high */
    run(10);
    CHECK(!inputs_lamps(0).turn_left);           /* 10 ms is not enough */
    run(20);
    CHECK(inputs_lamps(0).turn_left && !inputs_lamps(0).turn_right);
    fake_lamps = 0x01u | 0x20u;
    run(40);
    l = inputs_lamps(0);
    CHECK(l.turn_left && l.oil && !l.brake);
    /* a 5 ms glitch on the brake lamp input never gets through */
    fake_lamps |= 0x08u; run(10); fake_lamps &= (uint8_t)~0x08u; run(40);
    CHECK(!inputs_lamps(0).brake);
    /* bit 2 of the invert mask: the high-beam lamp is ground-switched (idles high, active low) */
    fake_lamps = 0x04u; run(60);
    CHECK(!inputs_lamps(0x04u).high_beam && inputs_lamps(0).high_beam);       /* pin high = lamp off when inverted */
    fake_lamps = 0x00u; run(60);
    CHECK(inputs_lamps(0x04u).high_beam && !inputs_lamps(0).high_beam);
    /* a flashing turn signal at 1.5 Hz follows the flasher */
    int on_transitions = 0; bool prev = false;
    for (int i = 0; i < 300; i++) {
        fake_lamps = ((i / 33) % 2) ? 0x02u : 0x00u;                          /* about 330 ms on, 330 ms off */
        run(10);
        bool now_on = inputs_lamps(0).turn_right;
        if (now_on && !prev) on_transitions++;
        prev = now_on;
    }
    CHECK(on_transitions >= 4);
}

static void test_ignition_and_dimmer(void)
{
    begin();
    run(100);
    CHECK(!inputs_ignition_on());
    fake_ign = true; run(30);
    CHECK(!inputs_ignition_on());                                             /* a 30 ms blip is not a key turn */
    run(40);
    CHECK(inputs_ignition_on());
    fake_ign = false; run(30);
    CHECK(inputs_ignition_on());                                              /* a crank dip does not switch the cluster off */
    fake_ign = true; run(100);
    CHECK(inputs_ignition_on());
    fake_ign = false; run(100);
    CHECK(!inputs_ignition_on());

    /* lights on or off: divider 0.176, VREF 3.3 V; a feed of 2 V is 352 mV on the pin = code 437 */
    fake_adc[ADC_CH_DIMMER] = 400; run(300);                                  /* 0.32 V on the pin = 1.8 V feed: switched off */
    CHECK(!inputs_dash_lights_on());
    fake_adc[ADC_CH_DIMMER] = 900; run(300);                                  /* 0.73 V on the pin = 4.1 V feed: lit */
    CHECK(inputs_dash_lights_on());
    adc_fail_mask = 1u << ADC_CH_DIMMER; run(300);
    CHECK(inputs_dash_lights_on());                                           /* a failed conversion keeps the last good state ... */
    adc_fail_mask = 0; fake_adc[ADC_CH_DIMMER] = 100; run(300);
    CHECK(!inputs_dash_lights_on());
    adc_fail_mask = 1u << ADC_CH_DIMMER; run(300);
    CHECK(!inputs_dash_lights_on());                                          /* ... whichever state that was */
    adc_fail_mask = 0;
}

static double dim_expect(double rheo)
{
    double f = 1.0 - (rheo - IM_DIM_RHEO_TOP_OHM) / (IM_DIM_RHEO_FULL_OHM - IM_DIM_RHEO_TOP_OHM);
    return f < 0.0 ? 0.0 : (f > 1.0 ? 100.0 : f * 100.0);
}

static void dim_setup(void)
{
    begin();
    dim_model = true; m_batt = 12.6; m_rheo = 0.1; m_bulb = 0.0; m_drop = IM_DIM_LOAD_DROP_V;
    m_lights = true; m_load = false; m_pulses = 0; m_noise = 0;
}

/* The whole path: the state machine, the ADC, the sum, against the circuit. */
static void test_dimmer(void)
{
    /* lights off: no pulses at all, however long, and nothing lit */
    dim_setup();
    m_lights = false;
    run(5000);
    CHECK(m_pulses == 0u && !m_load && !inputs_dash_lights_on() && inputs_dimmer_pct() == 0u);

    /* no bulbs on the feed, the case the circuit exists for: the feed reads the battery at every position, and the knob still reads */
    m_lights = true;
    static const double knob[] = { 0.1, 1.0, 3.0, 6.25, 9.0, 11.0, 12.0, 15.0, 9.0, 3.0, 0.1 };   /* down, and back up */
    for (unsigned i = 0; i < sizeof knob / sizeof knob[0]; i++) {
        m_rheo = knob[i];
        run(4000);
        CHECK(inputs_dash_lights_on());
        NEAR(inputs_dimmer_pct(), dim_expect(knob[i]), 3.0);
    }

    /* the engine starting moves the battery by more than the whole knob moves the feed: the reading must not care */
    dim_setup();
    m_rheo = 6.25;
    run(4000);
    NEAR(inputs_dimmer_pct(), 50.0, 3.0);
    unsigned before = inputs_dimmer_pct();
    m_batt = 14.4; run(4000);
    NEAR(inputs_dimmer_pct(), before, 3.0);
    m_batt = 11.8; run(4000);
    NEAR(inputs_dimmer_pct(), before, 3.0);

    /* bulbs still on the feed (radio, heater, clock): the same knob position reads the same */
    dim_setup();
    m_bulb = 20.0;
    m_rheo = 0.1; run(4000);
    NEAR(inputs_dimmer_pct(), 100.0, 2.0);
    m_rheo = 6.25; run(4000);
    NEAR(inputs_dimmer_pct(), 50.0, 4.0);
    /* and knob well down on bulbs, where the sag is too small to read: the low feed itself says so */
    m_bulb = 6.0; m_rheo = 15.0; run(4000);
    CHECK(inputs_dash_lights_on() && inputs_dimmer_pct() == 0u);

    /* the two diodes and Q4 are not exactly 1.8 V: +-0.4 V is about +-3 % of the load current */
    for (int d = -1; d <= 1; d += 2) {
        dim_setup();
        m_drop = IM_DIM_LOAD_DROP_V + d * 0.4;
        m_rheo = 6.25; run(4000);
        NEAR(inputs_dimmer_pct(), 50.0, 4.0);
    }

    /* the load: one poll on, 24 off, so 4 % of the time and never two polls running. It heats R105 for 10 ms, not for good. */
    dim_setup();
    m_rheo = 6.25;
    unsigned on = 0, run_on = 0, longest = 0;
    for (int i = 0; i < 2500; i++) {
        ms += 10u; fake_us += 10000u; inputs_poll(ms);
        if (m_load) { on++; if (++run_on > longest) longest = run_on; } else run_on = 0;
    }
    CHECK(on >= 95u && on <= 105u);
    CHECK(longest == 1u);

    /* whatever goes wrong during a pulse, the load comes off at the next poll */
    dim_setup();
    while (!m_load) { ms += 10u; fake_us += 10000u; inputs_poll(ms); }
    adc_fail_mask = 1u << ADC_CH_DIMMER;
    ms += 10u; fake_us += 10000u; inputs_poll(ms);
    CHECK(!m_load);
    adc_fail_mask = 0;
    /* a lost battery reading: it carries on, with the bulbs left in the sum */
    dim_setup();
    m_rheo = 6.25;
    adc_fail_mask = 1u << ADC_CH_BATT;
    run(4000);
    NEAR(inputs_dimmer_pct(), 50.0, 3.0);
    adc_fail_mask = 0;
    /* a lost feed reading before the pulse: no pulse */
    dim_setup();
    adc_fail_mask = 1u << ADC_CH_DIMMER;
    run(2000);
    CHECK(m_pulses == 0u);
    adc_fail_mask = 0;
    /* the lights go off during a pulse: off, and a valid reading of 0 at the next look */
    dim_setup();
    run(1000);
    while (!m_load) { ms += 10u; fake_us += 10000u; inputs_poll(ms); }
    m_lights = false;
    run(1000);
    CHECK(!m_load && !inputs_dash_lights_on() && inputs_dimmer_pct() == 0u);

    /* for main.c: the task can be stopped with the load on, and for the init */
    dim_setup();
    while (!m_load) { ms += 10u; fake_us += 10000u; inputs_poll(ms); }
    inputs_dim_load_off();
    CHECK(!m_load);
    m_load = true;
    inputs_init(&HW, &ADC);
    CHECK(!m_load);

    /* a part with no test load fitted (the null operation): no crash */
    static const inputs_hw_t NO_LOAD = { f_now, f_lamps, f_ign, f_lock, f_unlock, 0 };
    dim_setup();
    inputs_init(&NO_LOAD, &ADC);
    inputs_configure(16000u, 4u);
    run(1000);
    CHECK(inputs_dash_lights_on());

    /* a charging system well above normal stays on scale, so the knob still reads */
    dim_setup();
    m_rheo = 6.25;
    m_batt = 16.0;
    run(4000);
    NEAR(inputs_dimmer_pct(), 50.0, 3.0);

    /* the lights go off and the knob moves while they are off: the first reading afterwards is the new position, not a slow climb from the old one */
    dim_setup();
    m_rheo = 6.25;
    run(4000);
    m_lights = false;
    run(1000);
    m_rheo = 0.1;
    m_lights = true;
    run(300);
    CHECK(inputs_dash_lights_on() && inputs_dimmer_pct() == 100u);

    /* noise: +-4 ADC counts on every reading, which is 18 mV on the feed. Unfiltered that is about 3.8 % RMS on the reading; the filter
     * takes it under 2.6 %, and it does not hunt beyond a few percent */
    dim_setup();
    m_noise = 4;
    m_rheo = 6.25;
    run(4000);
    unsigned lo = 100u, hi = 0u;
    double sq = 0.0;
    for (int i = 0; i < 400; i++) {
        run(250);
        unsigned p = inputs_dimmer_pct();
        if (p < lo) lo = p;
        if (p > hi) hi = p;
        sq += ((double)p - 50.0) * ((double)p - 50.0);
    }
    CHECK(lo >= 38u && hi <= 62u);
    CHECK(sqrt(sq / 400.0) < 2.6);
    /* at the top of the knob the same noise must not dim it noticeably */
    m_rheo = 0.1; run(4000);
    CHECK(inputs_dimmer_pct() >= 92u);

    m_noise = 0;
    dim_model = false;
}

static void test_dead_inputs(void)
{
    inputs_init(0, 0);
    inputs_poll(10); inputs_poll(20);
    CHECK(!inputs_speed_kph().valid && !inputs_ignition_on() && !inputs_dash_lights_on());
    lamps_t l = inputs_lamps(0xFF);
    CHECK(l.turn_left && l.oil);                       /* all inverted and nothing read: an all-off input set shows lamps on ... */
    l = inputs_lamps(0x00);
    CHECK(!l.turn_left && !l.oil);
}

/* ---- senders.c ---------------------------------------------------------------------------------------------- */
/* A model of the gauges/ front end (senders.h): sender i is true_r[i] ohms (INFINITY = open wire) to its own ground, which
 * sits true_g[i] volts from this board's ground; 1 k pull-up to the excitation rail (3.3 V, or floating and joined to the
 * other two channels' pull-ups), 1 k series to the ADC pin, 6.8 k bias from the pin to 3.3 V. Everything in units of the
 * 3.3 V reference. The bias acts on the node as 7.8 k to the rail. */
static double true_r[3] = { 40.0, 30.0, 150.0 }, true_g[3] = { 0.0, 0.0, 0.0 };
static bool exc_on = true;
static unsigned excite_calls;
static void f_excite(bool on) { exc_on = on; excite_calls++; }
static const sender_hw_t SHW = { f_excite };

static void model_nodes(double vs[3])
{
    const double rpu = 1000.0, rb = 6800.0 + 1000.0;
    double vr = 1.0;
    for (int it = 0; it < 200; it++) {
        double sum = 0.0;
        for (int i = 0; i < 3; i++) {
            double top = exc_on ? 1.0 : vr;                         /* the pull-up's far end: the rail, or the floating rail */
            double g = 1.0 / rpu + 1.0 / rb, num = top / rpu + 1.0 / rb;
            if (isfinite(true_r[i])) { g += 1.0 / true_r[i]; num += (true_g[i] / 3.3) / true_r[i]; }
            vs[i] = num / g;
            sum += vs[i];
        }
        if (exc_on) break;
        vr = sum / 3.0;                                             /* the floating rail settles at the mean of the three nodes */
    }
}

static uint16_t model_code(adc_ch_t ch)
{
    double vs[3];
    model_nodes(vs);
    double va = vs[ch] + (1.0 - vs[ch]) * 1000.0 / 7800.0;
    if (va < 0.0) va = 0.0;                                         /* the converter reads zero below its reference */
    if (va > 1.0) va = 1.0;
    return (uint16_t)(4095.0 * va + 0.5);
}

static void sender_run(uint32_t n_ms)
{
    for (uint32_t i = 0; i < n_ms; i += 10) { ms += 10u; senders_poll(ms); }
}

static void set_senders(double rf, double ro, double rt, double gf_mv, double go_mv, double gt_mv)
{
    true_r[0] = rf; true_r[1] = ro; true_r[2] = rt;
    true_g[0] = gf_mv / 1000.0; true_g[1] = go_mv / 1000.0; true_g[2] = gt_mv / 1000.0;
}

static const sender_pt_t FUEL[] = { { 10.0f, 100.0f }, { 40.0f, 50.0f }, { 73.0f, 0.0f } };      /* made-up shape for the tests */

static void test_senders(void)
{
    ms = 1000;
    memset(fake_adc, 0, sizeof fake_adc); adc_fail_mask = 0;
    sender_model = true; exc_on = false; excite_calls = 0;
    senders_init(&ADC, &SHW);
    CHECK(exc_on && excite_calls == 1u);                               /* the excitation starts on */
    fake_adc[ADC_CH_BATT] = (uint16_t)(13.8 / BATT_DIVIDER / 3.3 * 4095.0 + 0.5);
    set_senders(40.0, 30.0, 150.0, 0.0, 0.0, 0.0);
    sender_run(1000);
    CHECK(excite_calls > 90u);                                          /* it is chopped every poll */
    CHECK(!senders_fuel_pct().valid);                                  /* no curve: invalid, but the resistance is known */
    NEAR(senders_ohms(SENDER_FUEL), 40.0, 0.3);
    NEAR(senders_ohms(SENDER_OIL), 30.0, 0.3);
    NEAR(senders_ohms(SENDER_COOLANT), 150.0, 1.0);
    sample_t b = senders_battery_v();
    CHECK(b.valid);
    NEAR(b.value, 13.8, 0.02);

    /* the reason for chopping: a hot engine (10-12 ohm) with its block 50 mV below this board's ground. A single-ended
     * reading puts the sender node near -17 mV, which used to read as a shorted sender */
    set_senders(10.0, 10.0, 12.0, 0.0, -50.0, -50.0);
    sender_run(20000);
    NEAR(senders_ohms(SENDER_OIL), 10.0, 0.4);
    NEAR(senders_ohms(SENDER_COOLANT), 12.0, 0.4);
    NEAR(senders_ground_mv(SENDER_COOLANT), -50.0, 3.0);
    CHECK(senders_short_mask() == 0u && senders_open_mask() == 0u);
    /* offsets of either sign and different on each sender: a corroded engine strap and the body ground at the tank */
    set_senders(73.0, 40.0, 300.0, 120.0, -300.0, -420.0);
    sender_run(30000);
    NEAR(senders_ohms(SENDER_FUEL), 73.0, 0.6);
    NEAR(senders_ohms(SENDER_OIL), 40.0, 0.6);
    NEAR(senders_ohms(SENDER_COOLANT), 300.0, 2.5);
    NEAR(senders_ground_mv(SENDER_FUEL), 120.0, 5.0);
    NEAR(senders_ground_mv(SENDER_OIL), -300.0, 5.0);
    CHECK(senders_open_mask() == 0u);

    set_senders(40.0, 30.0, 150.0, -40.0, -40.0, -40.0);
    senders_set_curve(SENDER_FUEL, FUEL, 3);
    sender_run(30000);
    CHECK(senders_fuel_pct().valid);
    NEAR(senders_fuel_pct().value, 50.0, 1.5);
    set_senders(25.0, 30.0, 150.0, -40.0, -40.0, -40.0);
    sender_run(60000);
    NEAR(senders_fuel_pct().value, 75.0, 2.0);                         /* between points, linear */
    set_senders(5.0, 30.0, 150.0, -40.0, -40.0, -40.0);
    sender_run(60000);
    NEAR(senders_fuel_pct().value, 100.0, 0.5);                        /* below the table clamps */

    /* damping: the fuel reading takes several seconds to follow a step, the oil reading under a second */
    senders_set_curve(SENDER_OIL, (const sender_pt_t[]){ { 10.0f, 0.0f }, { 70.0f, 600.0f } }, 2);
    set_senders(73.0, 70.0, 150.0, -40.0, -40.0, -40.0);
    sender_run(1000);
    CHECK(senders_fuel_pct().value > 50.0f);                           /* barely started: it was at 100 and has not got to 0 */
    CHECK(senders_oil_kpa().value > 450.0f);
    sender_run(20000);
    CHECK(senders_fuel_pct().value < 3.0f);

    /* an open wire is reported after about 1 s and then invalid; reconnecting clears it */
    set_senders(73.0, INFINITY, 150.0, -40.0, -40.0, -40.0);
    sender_run(300);
    CHECK((senders_open_mask() & 2u) == 0u);
    sender_run(1500);
    CHECK((senders_open_mask() & 2u) != 0u && !senders_oil_kpa().valid);
    CHECK(senders_ohms(SENDER_OIL) < 0.0f);
    set_senders(73.0, 50.0, 150.0, -40.0, -40.0, -40.0);
    sender_run(3000);
    CHECK(senders_open_mask() == 0u && senders_oil_kpa().valid);
    set_senders(73.0, 90000.0, 150.0, 0.0, 0.0, 0.0);                  /* a poor connection is open too */
    sender_run(3000);
    CHECK((senders_open_mask() & 2u) != 0u);
    set_senders(73.0, 20000.0, 150.0, 0.0, 0.0, 0.0);                  /* 20 kOhm: high, but a real reading */
    sender_run(3000);
    CHECK((senders_open_mask() & 2u) == 0u);
    set_senders(73.0, 50.0, 150.0, 0.0, 0.0, 0.0);
    sender_run(3000);
    /* a short to ground, at the sender's ground: found once the coolant filter (1.3 s) has followed the step */
    set_senders(73.0, 50.0, 0.3, 0.0, 0.0, -60.0);
    sender_run(15000);
    CHECK((senders_short_mask() & 4u) != 0u && (senders_open_mask() & 4u) == 0u);
    /* a ground offset beyond what the bias can lift: reported (in the open mask, as "no reading") and invalid */
    set_senders(73.0, 50.0, 150.0, 0.0, 0.0, -700.0);
    sender_run(5000);
    CHECK((senders_ground_fault_mask() & 4u) != 0u && (senders_open_mask() & 4u) != 0u && !senders_coolant_c().valid);
    set_senders(73.0, 50.0, 150.0, 0.0, 0.0, 0.0);
    sender_run(5000);
    CHECK(senders_ground_fault_mask() == 0u && senders_short_mask() == 0u);
    /* a converter that stops answering: the value goes stale after 2 s */
    adc_fail_mask = 1u << ADC_CH_BATT;
    sender_run(1000);
    CHECK(senders_battery_v().valid);
    sender_run(3000);
    CHECK(!senders_battery_v().valid);
    adc_fail_mask = 0;
    /* nothing at all */
    senders_init(0, 0);
    senders_poll(5);
    CHECK(!senders_battery_v().valid && !senders_fuel_pct().valid);
    senders_init(&ADC, 0);                                              /* no excitation switch: a dead set too */
    senders_poll(15);
    CHECK(!senders_battery_v().valid);
    sender_model = false;
}

int main(void)
{
    test_capture_extend();
    test_capture_states();
    test_speed();
    test_vr_speed();
    test_tach();
    test_lamps();
    test_ignition_and_dimmer();
    test_dimmer();
    test_dead_inputs();
    test_senders();
    if (failures) { printf("test_inputs: %d FAILED\n", failures); return 1; }
    printf("test_inputs: ok\n");
    return 0;
}
