// Vehicle values from the private link, as LIVI's telemetry push (HTTP POST /telemetry on port 4000,
// a JSON object merged field by field into LIVI's snapshot). LIVI draws its dashboard from it and passes
// speed, lights, night mode and the rest on to Android Auto and CarPlay. Pure C++17.
//
// Field names are LIVI's TelemetrySnapshot (src/main/shared/core/contract.ts, checked against LIVI
// 9.5.0, 2026-10-17). A value whose message is stale or flagged invalid is sent as null, so LIVI never
// keeps showing a number that is no longer true. Oil pressure has no LIVI field and is not sent.
#pragma once

#include <string>

#include "bridge.h"

namespace clusterd {

std::string telemetry_json(const vhal::Bridge& b, uint32_t now_ms);

// {"path":"/custom"}: LIVI opens that page once each time the path changes.
std::string path_json(const char* path);

// Frames for LIVI's core socket ($XDG_RUNTIME_DIR/livi/core.sock, livi-core-proto frame.rs): a little-endian
// uint32 byte count, then JSON. The hello first (LIVI_CORE_PROTOCOL is livi-core-proto's PROTOCOL, 8 in LIVI 9.5.0),
// then a key as LIVI's renderer reports it: KeyboardEvent.code, which LIVI maps through its key bindings (knobLeft F13,
// knobRight F14, selectDown Enter, selectUp F15, back Backspace, set by livi_config.py) and passes to Android Auto or
// CarPlay. LIVI hands Android Auto only the press of a key, so a click is two keys: selectDown (DPAD_CENTER down), then
// selectUp (DPAD_CENTER up); without the second the phone sees the centre button held and never clicks.
constexpr unsigned LIVI_CORE_PROTOCOL = 8;
std::string livi_hello_frame(const char* client);
std::string livi_key_frame(const char* code, bool down);

// The Android app's telemetry line (core/Telemetry.java, "CL1 imperial=1 theme=1 center=0 speed=96.56 ..."), the
// format gauges-fw's host harness takes on UDP 5005. Bench use: one replayed drive moves LIVI's centre and the
// four small gauges together. '-' = not available. Units are gauges-fw's: km/h, rpm, V, %, degC, kPa.
std::string harness_line(const vhal::Bridge& b, uint32_t now_ms, bool imperial, int theme, bool centre_speed);

}  // namespace clusterd
