#include <stdio.h>
#include "aggregate.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)

static sample_t S(float v, bool ok, uint32_t t) { sample_t s = { v, ok, t }; return s; }

int main(void)
{
    /* freshness, including a 32-bit millisecond wrap */
    CHECK(agg_fresh(S(1, true, 1000), 1400, 500));
    CHECK(!agg_fresh(S(1, true, 1000), 1600, 500));
    CHECK(!agg_fresh(S(1, false, 1000), 1100, 500));
    CHECK(agg_fresh(S(1, true, 0xFFFFFF00u), 0x00000100u, 600));

    /* fluids: fresh car value wins, stale car falls back to local */
    chosen_t c = agg_pick_car_first(S(50, true, 900), S(40, true, 900), 1000, 500);
    CHECK(c.valid && c.src == SRC_CAR && c.value == 50);
    c = agg_pick_car_first(S(50, true, 100), S(40, true, 900), 1000, 500);
    CHECK(c.valid && c.src == SRC_LOCAL && c.value == 40);
    c = agg_pick_car_first(S(50, true, 100), S(40, false, 900), 1000, 500);
    CHECK(!c.valid && c.src == SRC_NONE);

    /* speed: plausible Hall wins; implausible Hall falls to the car bus */
    c = agg_pick_speed(S(88, true, 0), S(90, true, 990), 1000, 500);
    CHECK(c.src == SRC_LOCAL && c.value == 88);
    c = agg_pick_speed(S(900, true, 0), S(90, true, 990), 1000, 500);
    CHECK(c.src == SRC_CAR && c.value == 90);
    c = agg_pick_speed(S(0, false, 0), S(90, true, 100), 1000, 500);
    CHECK(!c.valid);

    /* rpm: tach only when enabled and fresh */
    c = agg_pick_rpm(S(3000, true, 990), true, S(3100, true, 990), 1000, 500, 200);
    CHECK(c.src == SRC_LOCAL && c.value == 3000);
    c = agg_pick_rpm(S(3000, true, 990), false, S(3100, true, 990), 1000, 500, 200);
    CHECK(c.src == SRC_CAR && c.value == 3100);
    c = agg_pick_rpm(S(3000, true, 100), true, S(3100, true, 990), 1000, 500, 200);
    CHECK(c.src == SRC_CAR);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("aggregate: all tests passed\n");
    return 0;
}
