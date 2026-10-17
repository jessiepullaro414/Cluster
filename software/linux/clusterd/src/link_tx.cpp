#include "link_tx.h"

extern "C" {
#include "cluster_codec.h"
}

namespace clusterd {

void LinkTx::set_display(const DisplayState& d) {
    if (d.brightness_pct != disp_.brightness_pct || d.night != disp_.night || d.units_mph != disp_.units_mph ||
        d.gauge_theme != disp_.gauge_theme || d.centre_shows_speed != disp_.centre_shows_speed)
        dirty_[kSettings] = true;
    disp_ = d;
}

void LinkTx::set_vehicle(const VehicleSetup& v) {
    if (v.car_profile != veh_.car_profile || v.car_bitrate != veh_.car_bitrate || v.tank_capacity_l != veh_.tank_capacity_l)
        dirty_[kSettings] = true;
    if (v.pulses_per_mile != veh_.pulses_per_mile) dirty_[kCalib] = true;
    if (v.lamp_invert_mask != veh_.lamp_invert_mask || v.tach_enabled != veh_.tach_enabled ||
        v.tach_pulses_per_rev != veh_.tach_pulses_per_rev)
        dirty_[kInput] = true;
    if (v.trip_reset_count != veh_.trip_reset_count) dirty_[kTrip] = true;
    veh_ = v;
}

void LinkTx::set_heartbeat(Heartbeat h) {
    if (h != hb_) dirty_[kHeartbeat] = true;
    hb_ = h;
}

void LinkTx::pack(int m, Frame* f) {
    uint8_t c = counter_[m];
    counter_[m] = uint8_t((c + 1) & 0x0F);
    switch (m) {
        case kSettings: {
            cluster_display_settings_t s = {};
            s.brightness_pct = disp_.brightness_pct;
            s.night_mode = disp_.night;
            s.units_mph = disp_.units_mph;
            s.gauge_theme = disp_.gauge_theme;
            s.center_shows_speed = disp_.centre_shows_speed;
            s.car_profile = veh_.car_profile;
            s.car_bitrate = veh_.car_bitrate;
            s.tank_capacity_l = veh_.tank_capacity_l;
            f->id = CAN_ID_DISPLAYSETTINGS;
            cluster_display_settings_pack(&s, c, f->data);
            break;
        }
        case kCalib: {
            cluster_speed_calibration_t s = {};
            s.pulses_per_mile = veh_.pulses_per_mile;
            f->id = CAN_ID_SPEEDCALIBRATION;
            cluster_speed_calibration_pack(&s, c, f->data);
            break;
        }
        case kInput: {
            cluster_input_config_t s = {};
            s.lamp_invert_mask = veh_.lamp_invert_mask;
            s.tach_enabled = veh_.tach_enabled;
            s.tach_pulses_per_rev = veh_.tach_pulses_per_rev;
            f->id = CAN_ID_INPUTCONFIG;
            cluster_input_config_pack(&s, c, f->data);
            break;
        }
        case kTrip: {
            cluster_trip_command_t s = {};
            s.trip_reset_count = veh_.trip_reset_count & 0x0F;
            f->id = CAN_ID_TRIPCOMMAND;
            cluster_trip_command_pack(&s, c, f->data);
            break;
        }
        default: {
            cluster_display_heartbeat_t s = {};
            s.state = uint32_t(hb_);
            f->id = CAN_ID_DISPLAYHEARTBEAT;
            cluster_display_heartbeat_pack(&s, c, f->data);
            break;
        }
    }
}

int LinkTx::poll(uint32_t now_ms, Frame* out) {
    int n = 0;
    for (int m = 0; m < kCount; m++) {
        bool due = !sent_once_[m] || dirty_[m] || now_ms - last_ms_[m] >= kPeriodMs;
        if (!due) continue;
        pack(m, &out[n++]);
        sent_once_[m] = true;
        dirty_[m] = false;
        last_ms_[m] = now_ms;
    }
    return n;
}

bool PowerPolicy::update(uint32_t now_ms, bool valid, bool suspend_request, uint32_t suspend_in_s) {
    if (!valid) return false;   // no news from gauges/: keep doing what we were doing
    if (!suspend_request) {
        pending_ = fired_ = false;
        return false;
    }
    if (fired_) return false;   // once per request; resumed() or a cleared request starts over
    if (!pending_) {
        pending_ = true;
        due_ms_ = now_ms + suspend_in_s * 1000u;
    }
    if (int32_t(now_ms - due_ms_) >= 0) {
        fired_ = true;
        return true;
    }
    return false;
}

}  // namespace clusterd
