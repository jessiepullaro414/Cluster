#include "state_io.h"

#include <cstdio>
#include <cstdlib>
#include <sstream>

namespace clusterd {

Phone parse_livi_phone(const std::string& s) {
    size_t p = s.find("\"projection\"");
    if (p == std::string::npos) return Phone::None;
    size_t a = s.find("\"active\"", p);
    if (a == std::string::npos) return Phone::None;
    size_t colon = s.find(':', a + 8);
    if (colon == std::string::npos) return Phone::None;
    size_t v = s.find_first_not_of(" \t\r\n", colon + 1);
    if (v == std::string::npos) return Phone::None;
    if (s.compare(v, 4, "\"cp\"") == 0) return Phone::CarPlay;
    if (s.compare(v, 4, "\"aa\"") == 0) return Phone::AndroidAuto;
    return Phone::None;
}

static std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
    return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

void parse_config(const std::string& text, Config* c) {
    std::istringstream in(text);
    std::string line;
    while (std::getline(in, line)) {
        size_t hash = line.find('#');
        if (hash != std::string::npos) line.resize(hash);
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = trim(line.substr(0, eq)), v = trim(line.substr(eq + 1));
        if (k.empty() || v.empty()) continue;
        long n = std::strtol(v.c_str(), nullptr, 0);
        float f = std::strtof(v.c_str(), nullptr);
        hmi::Model& m = c->model;
        VehicleSetup& veh = c->vehicle;
        if (k == "theme" && n >= 0 && n <= 3) m.theme = int(n);
        else if (k == "match_carplay") m.match_carplay = n != 0;
        else if (k == "imperial") m.imperial = n != 0;
        else if (k == "no_phone_home") m.no_phone_home = n != 0;
        else if (k == "map_shape" && n >= 0 && n <= 3) m.map_shape = int(n);
        else if (k == "brightness" && n >= 10 && n <= 100) m.brightness = int(n);
        else if (k == "car_profile" && n >= 0 && n <= 255) veh.car_profile = uint32_t(n);
        else if (k == "car_bitrate" && n >= 0 && n <= 2) veh.car_bitrate = uint32_t(n);
        else if (k == "tank_capacity_l" && f > 0 && f <= 200) veh.tank_capacity_l = f;
        else if (k == "pulses_per_mile" && n >= 100 && n <= 200000) veh.pulses_per_mile = uint32_t(n);
        else if (k == "lamp_invert_mask" && n >= 0 && n <= 63) veh.lamp_invert_mask = uint32_t(n);
        else if (k == "tach_enabled") veh.tach_enabled = n != 0;
        else if (k == "tach_pulses_per_rev" && n >= 1 && n <= 16) veh.tach_pulses_per_rev = uint32_t(n);
        else if (k == "trip_reset_count" && n >= 0 && n <= 15) veh.trip_reset_count = uint32_t(n);
        else if (k == "can_if") c->can_if = v;
        else if (k == "map_shape_cmd") c->map_shape_cmd = v;
        else if (k == "suspend_cmd") c->suspend_cmd = v;
        else if (k == "livi_port" && n > 0 && n < 65536) c->livi_port = int(n);
        else if (k == "page_port" && n > 0 && n < 65536) c->page_port = int(n);
        else if (c->dial && k == "dial_raw_min" && n >= 0) c->dial->raw_min = uint32_t(n);
        else if (c->dial && k == "dial_raw_max" && n > 0) c->dial->raw_max = uint32_t(n);
        else if (c->dial && k == "dial_detents" && n >= 4 && n <= 96) c->dial->detents_per_turn = int(n);
    }
}

std::string format_settings(const hmi::Model& m, const VehicleSetup& v) {
    char buf[256];
    std::snprintf(buf, sizeof buf,
                  "# written by clusterd: the settings the dial changes\n"
                  "theme = %d\nmatch_carplay = %d\nimperial = %d\nno_phone_home = %d\nmap_shape = %d\nbrightness = %d\n"
                  "trip_reset_count = %u\n",
                  m.theme, m.match_carplay ? 1 : 0, m.imperial ? 1 : 0, m.no_phone_home ? 1 : 0, m.map_shape, m.brightness,
                  unsigned(v.trip_reset_count & 0x0F));
    return buf;
}

bool parse_replay_line(const std::string& line, uint32_t* t_ms, uint32_t* id, uint8_t data[8], uint8_t* len) {
    std::istringstream in(line);
    std::string ts, ids, name;
    if (!(in >> ts >> ids >> name) || ts.size() < 2 || ts.back() != 's' || ids.compare(0, 2, "0x") != 0) return false;
    char* end = nullptr;
    double t = std::strtod(ts.c_str(), &end);
    if (end != ts.c_str() + ts.size() - 1 || t < 0) return false;
    unsigned long v = std::strtoul(ids.c_str() + 2, &end, 16);
    if (*end || v > 0x7FF) return false;
    uint8_t n = 0;
    std::string byte;
    while (in >> byte) {
        if (n == 8 || byte.size() != 2) return false;
        unsigned long b = std::strtoul(byte.c_str(), &end, 16);
        if (*end) return false;
        data[n++] = uint8_t(b);
    }
    if (n == 0) return false;
    *t_ms = uint32_t(t * 1000.0 + 0.5);
    *id = uint32_t(v);
    *len = n;
    return true;
}

static void json_str(std::string& s, const std::string& v) {
    s += '"';
    for (char ch : v) {
        if (ch == '"' || ch == '\\') s += '\\';
        if (static_cast<unsigned char>(ch) >= 0x20) s += ch;
    }
    s += '"';
}

std::string page_state_json(const Shell& sh) {
    const hmi::Ui& ui = sh.ui();
    std::string s = "{\"screen\":";
    s += ui.screen() == hmi::Screen::Home ? "\"home\"" : "\"settings\"";
    s += ",\"editing\":";
    s += ui.screen() == hmi::Screen::Edit ? "true" : "false";
    s += ",\"row\":" + std::to_string(int(ui.row()));
    s += ",\"rows\":[";
    for (int i = 0; i < hmi::kRows; i++) {
        if (i) s += ',';
        s += '[';
        json_str(s, hmi::label(hmi::Row(i)));
        s += ',';
        json_str(s, hmi::value(ui.model(), hmi::Row(i)));
        s += ']';
    }
    s += "],\"phone\":";
    s += sh.phone() == Phone::CarPlay ? "\"cp\"" : sh.phone() == Phone::AndroidAuto ? "\"aa\"" : "null";
    s += ",\"theme\":" + std::to_string(sh.gauge_theme());
    s += "}";
    return s;
}

}  // namespace clusterd
