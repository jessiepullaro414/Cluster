#include "telemetry.h"

#include <cmath>
#include <cstdio>

namespace clusterd {

using vhal::Prop;

static void add_num(std::string& s, const char* key, vhal::PropValue v, float scale, int decimals) {
    char buf[64];
    if (!v.available || !std::isfinite(v.value)) std::snprintf(buf, sizeof buf, "\"%s\":null,", key);
    else std::snprintf(buf, sizeof buf, "\"%s\":%.*f,", key, decimals, double(v.value * scale));
    s += buf;
}

static void add_bool(std::string& s, const char* key, vhal::PropValue v) {
    s += "\"";
    s += key;
    s += "\":";
    s += !v.available ? "null," : (v.value != 0.0f ? "true," : "false,");
}

std::string telemetry_json(const vhal::Bridge& b, uint32_t now_ms) {
    std::string s = "{";
    add_num(s, "speedKph", b.get(Prop::SpeedMps, now_ms), 3.6f, 1);
    add_num(s, "rpm", b.get(Prop::EngineRpm, now_ms), 1.0f, 0);
    add_num(s, "coolantC", b.get(Prop::CoolantC, now_ms), 1.0f, 1);
    add_num(s, "batteryV", b.get(Prop::BatteryV, now_ms), 1.0f, 2);
    add_num(s, "fuelPct", b.get(Prop::FuelPct, now_ms), 1.0f, 1);
    add_num(s, "dimmerPct", b.get(Prop::DashDimmerPct, now_ms), 1.0f, 0);
    add_bool(s, "highBeam", b.get(Prop::HighBeam, now_ms));
    vhal::PropValue lights = b.get(Prop::DashLightsOn, now_ms);
    add_bool(s, "lights", lights);
    add_bool(s, "nightMode", lights);   // the dash lights are on: night for LIVI, Android Auto and CarPlay

    vhal::PropValue l = b.get(Prop::TurnLeft, now_ms), r = b.get(Prop::TurnRight, now_ms);
    if (!l.available || !r.available) s += "\"turnSignal\":null,\"hazards\":null";
    else {
        bool lo = l.value != 0.0f, ro = r.value != 0.0f;
        s += "\"turnSignal\":\"";
        s += lo && !ro ? "left" : (ro && !lo ? "right" : "none");
        s += "\",\"hazards\":";
        s += lo && ro ? "true" : "false";
    }
    s += "}";
    return s;
}

std::string path_json(const char* path) {
    std::string s = "{\"path\":\"";
    for (const char* p = path; *p; p++)
        if (*p != '"' && *p != '\\') s += *p;
    s += "\"}";
    return s;
}

}  // namespace clusterd
