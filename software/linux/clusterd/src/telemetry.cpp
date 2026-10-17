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

static void line_num(std::string& s, const char* key, vhal::PropValue v, float scale, int decimals) {
    char buf[48];
    if (!v.available || !std::isfinite(v.value)) std::snprintf(buf, sizeof buf, " %s=-", key);
    else std::snprintf(buf, sizeof buf, " %s=%.*f", key, decimals, double(v.value * scale));
    s += buf;
}

static void line_flag(std::string& s, const char* key, vhal::PropValue v) {
    s += ' ';
    s += key;
    s += '=';
    s += !v.available ? '-' : (v.value != 0.0f ? '1' : '0');
}

std::string harness_line(const vhal::Bridge& b, uint32_t now_ms, bool imperial, int theme, bool centre_speed) {
    std::string s = "CL1 imperial=";
    s += imperial ? '1' : '0';
    s += " theme=" + std::to_string(theme);
    s += " center=";
    s += centre_speed ? '1' : '0';
    line_num(s, "speed", b.get(Prop::SpeedMps, now_ms), 3.6f, 2);
    line_num(s, "rpm", b.get(Prop::EngineRpm, now_ms), 1.0f, 0);
    line_num(s, "batt", b.get(Prop::BatteryV, now_ms), 1.0f, 2);
    line_num(s, "fuel", b.get(Prop::FuelPct, now_ms), 1.0f, 1);
    line_num(s, "cool", b.get(Prop::CoolantC, now_ms), 1.0f, 1);
    line_num(s, "oil", b.get(Prop::OilKpa, now_ms), 1.0f, 1);
    line_flag(s, "tl", b.get(Prop::TurnLeft, now_ms));
    line_flag(s, "tr", b.get(Prop::TurnRight, now_ms));
    line_flag(s, "hb", b.get(Prop::HighBeam, now_ms));
    line_flag(s, "br", b.get(Prop::BrakeWarning, now_ms));
    line_flag(s, "alt", b.get(Prop::AlternatorWarning, now_ms));
    line_flag(s, "oilw", b.get(Prop::OilWarning, now_ms));
    line_flag(s, "dash", b.get(Prop::DashLightsOn, now_ms));
    line_num(s, "dim", b.get(Prop::DashDimmerPct, now_ms), 1.0f, 0);
    return s;
}

static std::string core_frame(const std::string& json) {
    std::string f(4, '\0');
    uint32_t n = uint32_t(json.size());
    for (int i = 0; i < 4; i++) f[size_t(i)] = char((n >> (8 * i)) & 0xFF);
    return f + json;
}

std::string livi_hello_frame(const char* client) {
    return core_frame(std::string("{\"type\":\"hello\",\"protocol\":") + std::to_string(LIVI_CORE_PROTOCOL) +
                      ",\"client\":\"" + client + "\"}");
}

std::string livi_key_frame(const char* code, bool down) {
    return core_frame(std::string("{\"type\":\"input\",\"input\":{\"kind\":\"key\",\"code\":\"") + code + "\",\"down\":" +
                      (down ? "true" : "false") + "}}");
}

std::string path_json(const char* path) {
    std::string s = "{\"path\":\"";
    for (const char* p = path; *p; p++)
        if (*p != '"' && *p != '\\') s += *p;
    s += "\"}";
    return s;
}

}  // namespace clusterd
