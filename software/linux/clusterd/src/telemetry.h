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

}  // namespace clusterd
