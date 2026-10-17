// Dial interface logic for the centre (Android) screen: PROOF OF CONCEPT.
//
// Pure C++17, no drawing, no hardware, no Android. It models what the Piher PSC-360 with push-button
// gives (turn left or right, click, long press) and the menu flows the owner can try in the simulator
// (hmi_sim.cpp). In the car the dial reaches the Verdin as an analog angle (ADC) and a click switch
// (GPIO); a small piece of code turns those into the same `Input` events, and the Android app does what
// this file does. The flows here are a PROPOSAL to try and change, not a decision.
//
// Flows:
//   Home          click or turn: flip between maps and gauge   long press: open Settings
//   Settings      turn: move selection   click: edit the row (or Back)   long press: back to Home
//   (The small screens take the CarPlay look while a phone shows CarPlay, if "With CarPlay" is on.)
//   Edit a row    turn: change the value (theme and units apply at once to the small screens)
//                 click: keep it   long press: cancel, restore the old value
#pragma once

#include <array>
#include <cstdint>
#include <string>

namespace hmi {

enum class Input { TurnLeft, TurnRight, Click, LongPress };

// ---- from a push-button to Click / LongPress -------------------------------------------------

// Press and release times in milliseconds. A press held for kLongMs fires LongPress once, while it is still
// held (so the user gets the feedback without letting go); releasing after that does nothing. A shorter
// press fires Click on release. A release that comes kLongMs or more after the press, before any tick saw it
// (a busy loop), is still a LongPress, never a Click. Debounce is the caller's job (GPIO input filtering).
class ClickDetector {
public:
    static constexpr uint32_t kLongMs = 600;

    // Returns true and sets out when an event fires. Call press() / release() on edges, tick() regularly.
    bool press(uint32_t now_ms) { down_ = true; fired_ = false; t_down_ = now_ms; return false; }
    bool tick(uint32_t now_ms, Input* out) {
        if (down_ && !fired_ && now_ms - t_down_ >= kLongMs) { fired_ = true; *out = Input::LongPress; return true; }
        return false;
    }
    bool release(uint32_t now_ms, Input* out) {
        bool was_down = down_;
        down_ = false;
        if (!was_down || fired_) return false;
        fired_ = true;
        *out = now_ms - t_down_ >= kLongMs ? Input::LongPress : Input::Click;
        return true;
    }
    bool held() const { return down_; }
    // 0..1 progress towards a long press while held, for a progress ring in the UI
    float long_progress(uint32_t now_ms) const {
        if (!down_ || fired_) return 0.0f;
        float p = float(now_ms - t_down_) / float(kLongMs);
        return p > 1.0f ? 1.0f : p;
    }

private:
    bool down_ = false, fired_ = false;
    uint32_t t_down_ = 0;
};

// ---- the settings -----------------------------------------------------------------------------

struct Model {
    int  theme = 1;                  // 0 classic, 1 modern, 2 CarPlay, 3 factory (DisplaySettings.GaugeTheme)
    bool match_carplay = true;       // while CarPlay is open the small screens take the Apple look
    bool imperial = true;
    bool no_phone_home = false;      // what to show with no phone: false gauge, true home
    int  map_shape = 0;              // 0 round, 1 square, 2 4:3, 3 16:9
    int  brightness = 100;           // percent, steps of 10
    bool operator==(const Model& o) const {
        return theme == o.theme && match_carplay == o.match_carplay && imperial == o.imperial && no_phone_home == o.no_phone_home &&
               map_shape == o.map_shape && brightness == o.brightness;
    }
};

enum class Row { Theme, MatchCarPlay, Units, NoPhone, MapShape, Brightness, Back, kCount };
constexpr int kRows = int(Row::kCount);

inline const char* label(Row r) {
    switch (r) {
        case Row::Theme: return "Gauge theme";
        case Row::MatchCarPlay: return "With CarPlay";
        case Row::Units: return "Units";
        case Row::NoPhone: return "No phone shows";
        case Row::MapShape: return "Map shape";
        case Row::Brightness: return "Brightness";
        default: return "Back";
    }
}

inline std::string value(const Model& m, Row r) {
    static const char* shapes[] = { "Round", "Square", "4:3", "16:9" };
    switch (r) {
        case Row::Theme: return m.theme == 0 ? "Classic" : m.theme == 1 ? "Modern" : m.theme == 2 ? "CarPlay" : "Factory";
        case Row::MatchCarPlay: return m.match_carplay ? "Apple look" : "My theme";
        case Row::Units: return m.imperial ? "mph, F, psi" : "km/h, C, kPa";
        case Row::NoPhone: return m.no_phone_home ? "Home" : "Gauge";
        case Row::MapShape: return shapes[m.map_shape & 3];
        case Row::Brightness: return std::to_string(m.brightness) + " %";
        default: return "";
    }
}

// Change a row's value by one step (dir = +1 / -1). Enumerations wrap; brightness stops at the ends.
inline void step(Model& m, Row r, int dir) {
    switch (r) {
        case Row::Theme: m.theme = ((m.theme + dir) % 4 + 4) % 4; break;
        case Row::MatchCarPlay: m.match_carplay = !m.match_carplay; break;
        case Row::Units: m.imperial = !m.imperial; break;
        case Row::NoPhone: m.no_phone_home = !m.no_phone_home; break;
        case Row::MapShape: m.map_shape = ((m.map_shape + dir) % 4 + 4) % 4; break;
        case Row::Brightness: {
            int b = m.brightness + 10 * dir;
            m.brightness = b < 10 ? 10 : (b > 100 ? 100 : b);
            break;
        }
        default: break;
    }
}

// What the small screens show: the owner's theme, except while CarPlay is open and "With CarPlay" is on.
inline int effective_theme(const Model& m, bool carplay_open) { return carplay_open && m.match_carplay ? 2 : m.theme; }

// ---- the state machine ------------------------------------------------------------------------

enum class Screen { Home, Settings, Edit };

class Ui {
public:
    Screen screen() const { return screen_; }
    Row row() const { return row_; }
    const Model& model() const { return model_; }          // the live values, including an edit in progress
    bool gauge_view() const { return gauge_view_; }        // Home: showing the gauge instead of the maps
    Model& mutable_model() { return model_; }              // for loading saved settings

    void handle(Input in) {
        switch (screen_) {
            case Screen::Home: home(in); break;
            case Screen::Settings: list(in); break;
            case Screen::Edit: edit(in); break;
        }
    }

    // True once after the settings changed for good (an edit was kept), so the caller can save them.
    bool take_committed() { bool c = committed_; committed_ = false; return c; }

private:
    void home(Input in) {
        if (in == Input::Click || in == Input::TurnLeft || in == Input::TurnRight) gauge_view_ = !gauge_view_;     // turn or click flips maps / gauge
        else if (in == Input::LongPress) { screen_ = Screen::Settings; row_ = Row::Theme; }
    }
    void list(Input in) {
        int n = kRows;
        switch (in) {
            case Input::TurnRight: row_ = Row((int(row_) + 1) % n); break;
            case Input::TurnLeft: row_ = Row((int(row_) + n - 1) % n); break;
            case Input::Click:
                if (row_ == Row::Back) screen_ = Screen::Home;
                else { before_ = model_; screen_ = Screen::Edit; }
                break;
            case Input::LongPress: screen_ = Screen::Home; break;
        }
    }
    void edit(Input in) {
        switch (in) {
            case Input::TurnRight: step(model_, row_, +1); break;
            case Input::TurnLeft: step(model_, row_, -1); break;
            case Input::Click:
                if (!(model_ == before_)) committed_ = true;
                screen_ = Screen::Settings;
                break;
            case Input::LongPress: model_ = before_; screen_ = Screen::Settings; break;
        }
    }

    Screen screen_ = Screen::Home;
    Row row_ = Row::Theme;
    Model model_, before_;
    bool gauge_view_ = false, committed_ = false;
};

}  // namespace hmi
