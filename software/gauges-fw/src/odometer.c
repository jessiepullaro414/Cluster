#include <string.h>
#include "odometer.h"

void odo_init(odo_t *o, const nv_ops_t *nv, uint32_t base_off)
{
    memset(o, 0, sizeof *o);
    o->save_step_m = ODO_SAVE_EVERY_M;
    uint32_t latest[2];
    if (nvlog_init(&o->log, nv, base_off, ODO_SECTORS, 8u, latest)) {
        o->odo_m = latest[0];
        o->trip_m = latest[1];
    }
    o->saved_odo_m = o->odo_m;
    o->saved_trip_m = o->trip_m;
    o->ign_prev = true;                          /* the first call to odo_ignition(false) is an edge to save */
}

void odo_tick(odo_t *o, uint32_t dt_ms, uint32_t speed_centi_kmh)
{
    if (dt_ms > 1000u) dt_ms = 1000u;            /* a stalled loop must not turn into a jump in distance */
    if (speed_centi_kmh > 40000u) speed_centi_kmh = 40000u;
    o->frac += speed_centi_kmh * dt_ms;          /* 0.01 km/h * ms; 360 of these are one millimetre (1 km/h = 0.27778 mm/ms) */
    uint32_t mm = o->frac / 360u;
    o->frac -= mm * 360u;
    o->mm_acc += mm;
    uint32_t m = o->mm_acc / 1000u;
    if (m != 0u) {
        o->mm_acc -= m * 1000u;
        o->odo_m += m;
        o->trip_m += m;
    }
}

void odo_ignition(odo_t *o, bool on)
{
    if (o->ign_prev && !on) o->flush = true;
    o->ign_prev = on;
}

void odo_trip_reset(odo_t *o)
{
    o->trip_m = 0u;
    o->flush = true;
}

static bool dirty(const odo_t *o)
{
    return o->odo_m != o->saved_odo_m || o->trip_m != o->saved_trip_m;
}

static bool save_due(const odo_t *o)
{
    if (!dirty(o)) return false;
    return o->flush || (o->odo_m - o->saved_odo_m) >= o->save_step_m;
}

bool odo_idle(const odo_t *o)
{
    if (nvlog_dead(&o->log)) return true;        /* the flash is not answering: waiting would never end */
    return !nvlog_busy(&o->log) && !dirty(o);
}

void odo_service(odo_t *o)
{
    nvlog_event_t ev = nvlog_service(&o->log);
    if (ev == NVLOG_EV_COMMITTED) {
        o->saved_odo_m = o->snap_odo_m;
        o->saved_trip_m = o->snap_trip_m;
    } else if (ev == NVLOG_EV_FAILED) {
        o->flush = true;                         /* what that entry should have held is still unsaved: try again at once */
    }
    if (save_due(o) && !nvlog_busy(&o->log)) {
        uint32_t payload[2] = { o->odo_m, o->trip_m };
        if (nvlog_write(&o->log, payload)) {
            o->snap_odo_m = payload[0];
            o->snap_trip_m = payload[1];
            o->flush = false;
            o->writes_started++;
        }
    }
}
