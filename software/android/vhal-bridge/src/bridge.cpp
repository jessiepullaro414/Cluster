#include "bridge.h"

extern "C" {
#include "cluster_can.h"
#include "cluster_codec.h"
}

namespace vhal {

namespace {
constexpr float kKphToMps = 1.0f / 3.6f;
}

Result Bridge::accept(Msg m, uint8_t counter, uint32_t now_ms) {
    Slot& s = slot_[m];
    if (s.seen) {
        const uint8_t step = static_cast<uint8_t>((counter - s.counter) & 0xF);
        if (step == 0) {
            stats_.repeated_counter++;
            return Result::RepeatedCounter;
        }
        stats_.missed_frames += static_cast<uint32_t>(step - 1);
    }
    s.seen = true;
    s.counter = counter;
    s.last_ms = now_ms;
    stats_.accepted++;
    return Result::Ok;
}

Result Bridge::on_frame(uint32_t id, const uint8_t* data, uint8_t len, uint32_t now_ms) {
    Msg msg;
    uint32_t period;
    switch (id) {
        case CAN_ID_VEHICLEMOTION: msg = kMotion; period = CAN_PERIOD_MS_VEHICLEMOTION; break;
        case CAN_ID_VEHICLEFLUIDS: msg = kFluids; period = CAN_PERIOD_MS_VEHICLEFLUIDS; break;
        case CAN_ID_INDICATORS: msg = kIndicators; period = CAN_PERIOD_MS_INDICATORS; break;
        case CAN_ID_POWERSTATE: msg = kPower; period = CAN_PERIOD_MS_POWERSTATE; break;
        default: return Result::UnknownId;
    }
    if (len != 8) {
        stats_.bad_length++;
        return Result::BadLength;
    }
    slot_[msg].period_ms = period;

    // Decode into a temporary first: nothing is committed unless the CRC holds
    // and the counter advanced.
    switch (msg) {
        case kMotion: {
            cluster_vehicle_motion_t d;
            if (cluster_vehicle_motion_unpack(data, &d) != 0) { stats_.bad_crc++; return Result::BadCrc; }
            const Result r = accept(msg, d.counter, now_ms);
            if (r != Result::Ok) return r;
            speed_kph_ = d.speed_kph; rpm_ = d.rpm; battery_v_ = d.battery_v;
            speed_ok_ = d.speed_valid; rpm_ok_ = d.rpm_valid; battery_ok_ = d.battery_valid;
            break;
        }
        case kFluids: {
            cluster_vehicle_fluids_t d;
            if (cluster_vehicle_fluids_unpack(data, &d) != 0) { stats_.bad_crc++; return Result::BadCrc; }
            const Result r = accept(msg, d.counter, now_ms);
            if (r != Result::Ok) return r;
            fuel_pct_ = d.fuel_pct; coolant_c_ = d.coolant_c; oil_kpa_ = d.oil_kpa;
            fuel_ok_ = d.fuel_valid; coolant_ok_ = d.coolant_valid; oil_ok_ = d.oil_valid;
            break;
        }
        case kIndicators: {
            cluster_indicators_t d;
            if (cluster_indicators_unpack(data, &d) != 0) { stats_.bad_crc++; return Result::BadCrc; }
            const Result r = accept(msg, d.counter, now_ms);
            if (r != Result::Ok) return r;
            turn_l_ = d.turn_left; turn_r_ = d.turn_right; high_ = d.high_beam; brake_ = d.brake_warning;
            alt_ = d.alternator_warning; oilw_ = d.oil_warning; dash_ = d.dash_lights_on;
            dimmer_ = d.dash_dimmer_pct;
            break;
        }
        case kPower: {
            cluster_power_state_t d;
            if (cluster_power_state_unpack(data, &d) != 0) { stats_.bad_crc++; return Result::BadCrc; }
            const Result r = accept(msg, d.counter, now_ms);
            if (r != Result::Ok) return r;
            ign_ = d.ignition_on; susp_ = d.suspend_request; suspend_s_ = d.suspend_in_seconds;
            break;
        }
        default: break;
    }
    return Result::Ok;
}

bool Bridge::fresh(Msg m, uint32_t now_ms) const {
    const Slot& s = slot_[m];
    if (!s.seen) return false;
    // unsigned subtraction: correct across the 2^32 ms wrap
    return static_cast<uint32_t>(now_ms - s.last_ms) <= kStaleFactor * s.period_ms;
}

bool Bridge::link_alive(uint32_t now_ms) const {
    return fresh(kMotion, now_ms) || fresh(kFluids, now_ms) || fresh(kIndicators, now_ms) || fresh(kPower, now_ms);
}

PropValue Bridge::get(Prop p, uint32_t now_ms) const {
    auto make = [](bool ok, float v) { PropValue r; r.available = ok; r.value = ok ? v : 0.0f; return r; };
    const bool mot = fresh(kMotion, now_ms), flu = fresh(kFluids, now_ms);
    const bool ind = fresh(kIndicators, now_ms), pwr = fresh(kPower, now_ms);
    switch (p) {
        case Prop::SpeedMps: return make(mot && speed_ok_, speed_kph_ * kKphToMps);
        case Prop::EngineRpm: return make(mot && rpm_ok_, static_cast<float>(rpm_));
        case Prop::BatteryV: return make(mot && battery_ok_, battery_v_);
        case Prop::FuelPct: return make(flu && fuel_ok_, fuel_pct_);
        case Prop::CoolantC: return make(flu && coolant_ok_, coolant_c_);
        case Prop::OilKpa: return make(flu && oil_ok_, oil_kpa_);
        case Prop::TurnLeft: return make(ind, turn_l_ ? 1.0f : 0.0f);
        case Prop::TurnRight: return make(ind, turn_r_ ? 1.0f : 0.0f);
        case Prop::HighBeam: return make(ind, high_ ? 1.0f : 0.0f);
        case Prop::BrakeWarning: return make(ind, brake_ ? 1.0f : 0.0f);
        case Prop::AlternatorWarning: return make(ind, alt_ ? 1.0f : 0.0f);
        case Prop::OilWarning: return make(ind, oilw_ ? 1.0f : 0.0f);
        case Prop::DashLightsOn: return make(ind, dash_ ? 1.0f : 0.0f);
        case Prop::DashDimmerPct: return make(ind, static_cast<float>(dimmer_));
        case Prop::IgnitionOn: return make(pwr, ign_ ? 1.0f : 0.0f);
        case Prop::SuspendRequest: return make(pwr, susp_ ? 1.0f : 0.0f);
        case Prop::SuspendInSeconds: return make(pwr, static_cast<float>(suspend_s_));
        default: return make(false, 0.0f);
    }
}

}  // namespace vhal
