#include "aggregate.h"

bool agg_fresh(sample_t s, uint32_t now_ms, uint32_t timeout_ms)
{
    /* unsigned subtraction is correct across a 32-bit millisecond wrap */
    return s.valid && (uint32_t)(now_ms - s.stamp_ms) <= timeout_ms;
}

static chosen_t none(void)
{
    chosen_t c = { 0.0f, false, SRC_NONE };
    return c;
}

static chosen_t from(sample_t s, source_t src)
{
    chosen_t c = { s.value, true, src };
    return c;
}

chosen_t agg_pick_car_first(sample_t car, sample_t local, uint32_t now_ms,
                            uint32_t car_timeout_ms)
{
    if (agg_fresh(car, now_ms, car_timeout_ms))
        return from(car, SRC_CAR);
    if (local.valid)
        return from(local, SRC_LOCAL);
    return none();
}

chosen_t agg_pick_speed(sample_t hall, sample_t car, uint32_t now_ms,
                        uint32_t car_timeout_ms)
{
    if (hall.valid && hall.value >= 0.0f && hall.value <= AGG_SPEED_MAX_KPH) {
        /* A Hall sender that reads standing still while a fresh car-bus speed says the car is moving has failed or lost its
         * wire (a stopped pulse train cannot be told from a dead one): believe the car bus. */
        if (hall.value < 1.0f && agg_fresh(car, now_ms, car_timeout_ms) && car.value >= AGG_HALL_ZERO_OVERRIDE_KPH)
            return from(car, SRC_CAR);
        return from(hall, SRC_LOCAL);
    }
    if (agg_fresh(car, now_ms, car_timeout_ms))
        return from(car, SRC_CAR);
    return none();
}

chosen_t agg_pick_rpm(sample_t tach, bool tach_enabled, sample_t car,
                      uint32_t now_ms, uint32_t car_timeout_ms,
                      uint32_t tach_timeout_ms)
{
    if (tach_enabled && agg_fresh(tach, now_ms, tach_timeout_ms) &&
        tach.value >= 0.0f && tach.value <= AGG_RPM_MAX)
        return from(tach, SRC_LOCAL);
    if (agg_fresh(car, now_ms, car_timeout_ms))
        return from(car, SRC_CAR);
    return none();
}
