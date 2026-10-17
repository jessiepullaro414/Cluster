// Text in and out of clusterd: LIVI's status file, the saved settings, and the state the settings page
// draws. Pure C++17 (strings in, strings out); main_linux.cpp does the file and socket I/O.
#pragma once

#include <string>

#include "bridge.h"
#include "dial_angle.h"
#include "link_tx.h"
#include "shell.h"

namespace clusterd {

// LIVI writes ~/.config/LIVI/state/status.json (livi-core status_file.rs), for example
//   {"ui":{"path":"/media"},"projection":{"active":"cp","streaming":true,"phoneType":"CarPlay"},...}
// "active" is "cp", "aa" or null. Only that field is read; anything unparsable reads as no phone.
Phone parse_livi_phone(const std::string& status_json);

// clusterd.conf / settings file: one "key = value" per line, '#' starts a comment. Unknown keys are
// ignored and missing ones keep their defaults, so an old file still loads.
struct Config {
    hmi::Model model;
    VehicleSetup vehicle;
    DialConfig* dial = nullptr;   // filled too when not null
    std::string can_if = "can1";  // the private link (Verdin CAN_1 on display/)
    std::string livi_url_host = "127.0.0.1";
    int livi_port = 4000;
    int page_port = 4010;          // clusterd's settings page, LIVI's customUrl
    // Run with the map shape number (0 round, 1 square, 2 4:3, 3 16:9) when the owner changes it; it
    // rewrites LIVI's projection safe area (../livi/livi_config.py --apply). Empty: do nothing.
    std::string map_shape_cmd;
    std::string suspend_cmd = "systemctl suspend";
};
void parse_config(const std::string& text, Config* c);
// Only what the dial changes (the model) and the trip counter; the rest of the file is the installer's.
std::string format_settings(const hmi::Model& m, const VehicleSetup& v);

// One line of tools/can_replay.py --dry-run output, "  1.234s  0x300  VehicleMotion      00 00 20 03 d8 04 0f 53",
// for the bench input --replay (a PC whose kernel has no virtual CAN). Returns false for anything else.
bool parse_replay_line(const std::string& line, uint32_t* t_ms, uint32_t* id, uint8_t data[8], uint8_t* len);

// The centre page (web/centre.html) polls GET /state and draws it:
//   {"view":"gauge","screen":"home","editing":false,"row":0,"rows":[["Gauge theme","Modern"],...],"phone":"cp",
//    "theme":1,"imperial":true,"veh":{"link":true,"speed_mps":12.5,"lights":false,"dimmer":40,"hi":false,
//    "brake":false,"alt":false,"oil":false}}
// "view" is maps, gauge or settings; a vehicle value that is stale or invalid is null.
std::string page_state_json(const Shell& sh, const vhal::Bridge& b, uint32_t now_ms);

}  // namespace clusterd
