#include "dial_angle.h"

namespace clusterd {

// Signed difference b - a on a circle, in -180..180.
static float wrap_delta(float a, float b) {
    float d = b - a;
    while (d > 180.0f) d -= 360.0f;
    while (d < -180.0f) d += 360.0f;
    return d;
}

int DialAngle::sample(uint32_t raw) {
    if (raw < c_.raw_min || raw > c_.raw_max || c_.raw_max <= c_.raw_min) return 0;
    float deg = 360.0f * float(raw - c_.raw_min) / float(c_.raw_max - c_.raw_min + 1);
    if (!have_) {
        have_ = true;
        last_deg_ = deg;
        travel_ = 0;
        return 0;
    }
    float d = wrap_delta(last_deg_, deg);
    if (d > kMaxJumpDeg || d < -kMaxJumpDeg) {
        // A glitch, not a hand. If the far reading persists (the sensor came back somewhere else),
        // take it as the new zero instead of rejecting it forever.
        if (++jumps_ >= kJumpsToRezero) { last_deg_ = deg; travel_ = 0; jumps_ = 0; }
        return 0;
    }
    jumps_ = 0;
    d *= c_.filter;
    last_deg_ += d;
    if (last_deg_ >= 360.0f) last_deg_ -= 360.0f;
    if (last_deg_ < 0.0f) last_deg_ += 360.0f;
    travel_ += d;

    const float step = 360.0f / float(c_.detents_per_turn);
    int steps = 0;
    while (travel_ >= step) { travel_ -= step; steps++; }
    while (travel_ <= -step) { travel_ += step; steps--; }
    return steps;
}

}  // namespace clusterd
