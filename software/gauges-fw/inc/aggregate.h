#ifndef AGGREGATE_H
#define AGGREGATE_H
/*
 * Source-priority aggregation (the gateway's brain). REAL, host-tested.
 * Rules from the plan: speed = Hall sender if present and plausible, else the
 * car bus; RPM = tach if enabled and fresh, else the car bus; fluids and
 * battery = a fresh car-bus value, else the local sender. Every result carries
 * a valid flag and its source so the UI can grey out a stale reading.
 */
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    float    value;
    bool     valid;       /* the producer says the value is usable */
    uint32_t stamp_ms;    /* time the value was last updated */
} sample_t;

typedef enum { SRC_NONE = 0, SRC_LOCAL = 1, SRC_CAR = 2 } source_t;

typedef struct {
    float    value;
    bool     valid;
    source_t src;
} chosen_t;

#define AGG_SPEED_MAX_KPH   400.0f   /* above this a Hall reading is implausible */
#define AGG_RPM_MAX         12000.0f

/* true when `now_ms - s.stamp_ms <= timeout_ms` (wrap-safe) and s.valid */
bool agg_fresh(sample_t s, uint32_t now_ms, uint32_t timeout_ms);

/* Fluids / battery: car value if fresh, else local if valid, else none. */
chosen_t agg_pick_car_first(sample_t car, sample_t local, uint32_t now_ms,
                            uint32_t car_timeout_ms);

/* Speed: local (Hall) if valid and plausible, else car, else none. */
chosen_t agg_pick_speed(sample_t hall, sample_t car, uint32_t now_ms,
                        uint32_t car_timeout_ms);

/* RPM: tach if enabled, fresh and plausible, else car, else none. */
chosen_t agg_pick_rpm(sample_t tach, bool tach_enabled, sample_t car,
                      uint32_t now_ms, uint32_t car_timeout_ms,
                      uint32_t tach_timeout_ms);

#endif
