// The Piher PSC-360 dial as turns: an endless 360-degree Hall angle (ratiometric analog, read on Verdin
// ADC_1 through display/'s divider) becomes +1 / -1 detent steps. Pure C++17.
//
//   * The angle is unwrapped across 0 / 360, so a turn through the seam is one smooth motion.
//   * A step fires when the angle has moved a whole detent from the last step's anchor; the anchor
//     then moves by exactly one detent, so slow turning cannot drift and a fast turn gives every step.
//   * Readings outside the sensor's valid band (raw_min..raw_max, e.g. a missing magnet or a broken
//     wire) are ignored, and so is any jump larger than kMaxJumpDeg between two samples.
//   * The first reading after start-up or a resume only sets the anchor (the sensor's 5 V is switched
//     off in sleep, rotary-service README), so waking never produces phantom turns.
//
// Detents are virtual: the PSC-360 has no mechanical clicks of its own. 24 per turn is a first guess.
#pragma once

#include <cstdint>

namespace clusterd {

struct DialConfig {
    uint32_t raw_min = 0;          // ADC counts at 0 degrees
    uint32_t raw_max = 4095;       // ADC counts just before 360 degrees
    int detents_per_turn = 24;
    float filter = 0.5f;           // first-order filter weight of a new sample, 1 = no filtering
};

class DialAngle {
public:
    static constexpr float kMaxJumpDeg = 90.0f;   // sampled every few ms, a hand cannot turn faster
    static constexpr int kJumpsToRezero = 3;      // this many far readings in a row: the sensor moved while off

    explicit DialAngle(const DialConfig& c = DialConfig()) : c_(c) {}

    // One ADC sample. Returns the number of detent steps it completed (positive = clockwise).
    int sample(uint32_t raw);

    // Forget the position (call after a resume); the next sample becomes the new zero.
    void rezero() { have_ = false; }

private:
    DialConfig c_;
    bool have_ = false;
    float last_deg_ = 0;   // filtered angle, 0..360
    float travel_ = 0;     // unwrapped travel since the anchor, degrees
    int jumps_ = 0;
};

}  // namespace clusterd
