// The centre screen's dial shell for the Linux option: which LIVI page is in front and where each dial
// event goes. Pure C++17, no hardware, no LIVI; main_linux.cpp turns the Actions into key presses and
// telemetry pushes.
//
// It is hmi-sim's dial state machine (../../hmi-sim/hmi.h, the flows the owner tries in the simulator)
// with one addition the real phone needs: while a phone is projecting and the maps are in front, the
// dial belongs to the phone.
//
//   Maps with a phone   turn: knob to the phone   click: select   hold 0.6 s: Back to the phone
//                       keep holding to 1.5 s: our speedometer (the owner asked for a way to it with a phone)
//   everything else     exactly hmi.h (Home: click or turn flips maps / gauge, hold: Settings; ...), so from
//                       the speedometer a turn or click goes back to the map and a 0.6 s hold opens Settings
//
// Which LIVI page shows what:
//   maps     LIVI "/"           the projection (or LIVI's own home with no phone)
//   gauge    LIVI "/custom"     clusterd's own page (web/centre.html) drawing OUR speedometer in the owner's theme
//                               (a port of the Android app's ClusterView), not LIVI's landscape dashboard
//   settings LIVI "/custom"     the same page, drawing the settings list; it only draws Shell state
//
// The 1.5 s second hold and "Back on hold" are a PROPOSAL like the rest of hmi.h: try them on the bench.
#pragma once

#include <cstdint>
#include <string>

#include "hmi.h"

namespace clusterd {

enum class Phone : uint8_t { None, CarPlay, AndroidAuto };
enum class Key : uint8_t { None, KnobLeft, KnobRight, Select, Back };

inline const char* kPathMaps = "/";
inline const char* kPathGauge = "/custom";
inline const char* kPathSettings = "/custom";

// What clusterd's own page draws (it is one LIVI page for both).
enum class View : uint8_t { Maps, Gauge, Settings };

struct Action {
    Key key = Key::None;          // a key for LIVI to pass to the phone
    const char* path = nullptr;   // a LIVI page to open (only when it changes)
};

class Shell {
public:
    static constexpr uint32_t kMenuHoldMs = 1500;

    // The page to open at start-up.
    Action start() {
        Action a;
        a.path = page_change();
        return a;
    }

    // A phone connected or left (from LIVI's state/status.json). A phone that arrives brings the maps
    // to the front, like CenterLogic does in the Android app.
    Action set_phone(Phone p) {
        Action a;
        if (p == phone_) return a;
        bool arrived = phone_ == Phone::None && p != Phone::None;
        phone_ = p;
        if (arrived && ui_.screen() == hmi::Screen::Home && ui_.gauge_view()) ui_.handle(hmi::Input::Click);
        a.path = page_change();
        return a;
    }

    // Raw click switch edges and a regular tick (every few ms); turns come from DialAngle.
    Action press(uint32_t now_ms) {
        click_.press(now_ms);
        menu_fired_ = false;
        return {};
    }
    Action release(uint32_t now_ms) {
        hmi::Input in;
        if (click_.release(now_ms, &in)) return input(in);
        return {};
    }
    Action tick(uint32_t now_ms) {
        hmi::Input in;
        if (click_.tick(now_ms, &in)) {
            t_long_ = now_ms;
            return input(in);
        }
        // Still held long after the first long press, on the maps with a phone: the way out to our speedometer.
        if (click_.held() && !menu_fired_ && phone_mode_at_long_ && now_ms - t_long_ >= kMenuHoldMs - hmi::ClickDetector::kLongMs) {
            menu_fired_ = true;
            phone_mode_at_long_ = false;
            ui_.handle(hmi::Input::Click);       // Home: maps -> gauge (hmi.h flips the view)
            Action a;
            a.path = page_change();
            return a;
        }
        return {};
    }
    Action turn(int dir) { return input(dir > 0 ? hmi::Input::TurnRight : hmi::Input::TurnLeft); }

    // Shown on the Settings page and sent to the gauges board.
    const hmi::Ui& ui() const { return ui_; }
    hmi::Ui& mutable_ui() { return ui_; }
    Phone phone() const { return phone_; }
    const char* path() const { return path_; }
    // Home shows the gauge or the maps. With a phone the maps come first; with none, the "No phone
    // shows" setting picks the first one. A click or turn on Home flips it either way (hmi.h).
    bool show_gauge() const {
        bool gauge_first = phone_ == Phone::None && !ui_.model().no_phone_home;
        return ui_.gauge_view() != gauge_first;
    }
    bool phone_owns_dial() const {
        return phone_ != Phone::None && ui_.screen() == hmi::Screen::Home && !show_gauge();
    }
    // The theme the small screens should show now (DisplaySettings.GaugeTheme).
    int gauge_theme() const { return hmi::effective_theme(ui_.model(), phone_ == Phone::CarPlay); }
    View view() const {
        if (ui_.screen() != hmi::Screen::Home) return View::Settings;
        return show_gauge() ? View::Gauge : View::Maps;
    }
    // The centre shows our speedometer, so the small screens need not repeat speed.
    bool centre_shows_speed() const { return view() == View::Gauge; }

private:
    Action input(hmi::Input in) {
        Action a;
        if (phone_owns_dial()) {
            phone_mode_at_long_ = in == hmi::Input::LongPress;
            switch (in) {
                case hmi::Input::TurnLeft: a.key = Key::KnobLeft; break;
                case hmi::Input::TurnRight: a.key = Key::KnobRight; break;
                case hmi::Input::Click: a.key = Key::Select; break;
                case hmi::Input::LongPress: a.key = Key::Back; break;
            }
            return a;
        }
        phone_mode_at_long_ = false;
        ui_.handle(in);
        a.path = page_change();
        return a;
    }

    // The page the state asks for, or nullptr when it is already in front.
    const char* page_change() {
        View v = view();
        const char* want = v == View::Settings ? kPathSettings : v == View::Gauge ? kPathGauge : kPathMaps;
        if (std::string(want) == path_) return nullptr;
        path_ = want;
        return want;
    }

    hmi::Ui ui_;
    hmi::ClickDetector click_;
    Phone phone_ = Phone::None;
    const char* path_ = "";
    uint32_t t_long_ = 0;
    bool menu_fired_ = false, phone_mode_at_long_ = false;
};

}  // namespace clusterd
