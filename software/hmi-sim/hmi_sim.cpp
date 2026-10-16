// Dial HMI simulator: PROOF OF CONCEPT. A desktop window with the round centre screen (what the Android app
// would draw) and the four small gauge screens (the real firmware screen code on a mock GC9A01 panel), driven
// by a simulated Piher PSC-360 dial: mouse wheel = turn, left button / Space / Enter = click, hold = long press.
//
//   hmi_sim                    interactive window (WSLg on Windows 11)
//   hmi_sim --selftest         state machine, click detector, drawing and small-screen checks; exit code = failures
//   hmi_sim --script "H,R,R,C,shot=a.png,C,L"
//                              headless: R/L turn right/left, C click, H hold; shot=file.png saves the window
// P: phone with CarPlay on/off (the small screens take the Apple look while it is open).
// Dial -> input in the car: the PSC-360's angle (ADC) turns into R/L steps, its switch (GPIO) goes through
// ClickDetector; both end up as hmi::Input, which is all this file's flow needs.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

extern "C" {
#include "aux_display.h"
#include "gfx.h"
#include "harness_x11.h"
#include "panel_mock.h"
#include "screens.h"
}
#include "hmi.h"

using namespace hmi;

// ---------------------------------------------------------------- geometry and colours
static const int C = 480;                     // centre screen canvas (the real one is 720x720; same layout, scaled)
static const int GAP = 16, SM = 240, HUD_H = 44;
static const int WIN_W = C + GAP + 2 * SM, WIN_H = C + HUD_H;

static const uint32_t COL_TEXT = 0xF2F4F7, COL_DIM = 0x8A94A3, COL_ACC = 0x35A7FF, COL_SEL = 0x1B2838,
                      COL_MAP = 0x18222D, COL_ROAD = 0x35424F, COL_BEZEL = 0x2A2F36, COL_RING = 0x232A33;

// ---------------------------------------------------------------- tiny PNG writer (stored deflate)
static uint32_t crc32_update(uint32_t crc, const uint8_t* p, size_t n) {
    crc = ~crc;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)-(int32_t)(crc & 1u));
    }
    return ~crc;
}
static void be32(uint8_t* o, uint32_t v) { o[0] = uint8_t(v >> 24); o[1] = uint8_t(v >> 16); o[2] = uint8_t(v >> 8); o[3] = uint8_t(v); }
static void png_chunk(FILE* f, const char* tag, const uint8_t* d, uint32_t n) {
    uint8_t h[8];
    be32(h, n);
    memcpy(h + 4, tag, 4);
    fwrite(h, 1, 8, f);
    if (n) fwrite(d, 1, n, f);
    uint32_t c = crc32_update(0, (const uint8_t*)tag, 4);
    c = crc32_update(c, d, n);
    uint8_t t[4];
    be32(t, c);
    fwrite(t, 1, 4, f);
}
static bool write_png(const char* path, const std::vector<uint32_t>& px, int w, int h) {
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    size_t row = 1 + size_t(w) * 3, raw_n = size_t(h) * row;
    std::vector<uint8_t> raw(raw_n);
    for (int y = 0; y < h; y++) {
        uint8_t* r = &raw[size_t(y) * row];
        *r++ = 0;
        for (int x = 0; x < w; x++) {
            uint32_t p = px[size_t(y) * w + x];
            *r++ = uint8_t(p >> 16); *r++ = uint8_t(p >> 8); *r++ = uint8_t(p);
        }
    }
    size_t blocks = (raw_n + 65534) / 65535;
    std::vector<uint8_t> z(2 + raw_n + blocks * 5 + 4);
    uint8_t* o = z.data();
    *o++ = 0x78; *o++ = 0x01;
    for (size_t off = 0; off < raw_n; off += 65535) {
        size_t n = raw_n - off > 65535 ? 65535 : raw_n - off;
        *o++ = (off + n >= raw_n) ? 1 : 0;
        *o++ = uint8_t(n); *o++ = uint8_t(n >> 8); *o++ = uint8_t(~n); *o++ = uint8_t(~n >> 8);
        memcpy(o, &raw[off], n);
        o += n;
    }
    uint32_t a = 1, b = 0;
    for (uint8_t v : raw) { a = (a + v) % 65521u; b = (b + a) % 65521u; }
    be32(o, (b << 16) | a);
    o += 4;
    uint8_t ihdr[13];
    be32(ihdr, uint32_t(w)); be32(ihdr + 4, uint32_t(h));
    ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = ihdr[11] = ihdr[12] = 0;
    fwrite("\x89PNG\r\n\x1a\n", 1, 8, f);
    png_chunk(f, "IHDR", ihdr, 13);
    png_chunk(f, "IDAT", z.data(), uint32_t(o - z.data()));
    png_chunk(f, "IEND", nullptr, 0);
    fclose(f);
    return true;
}

// ---------------------------------------------------------------- drawing the centre screen
struct Ops {
    op_t v[255];
    int n = 0, dropped = 0;
    void add(const op_t& o) { if (n < 250) v[n++] = o; else dropped++; }
    void text(const font_t* f, const std::string& s, int x, int base, text_align_t al, uint32_t col) {
        op_t t[64];
        int k = gfx_text(t, 64, f, s.c_str(), x, base, al, col);
        for (int i = 0; i < k; i++) add(t[i]);
    }
};

static float wrap360(float a) { while (a >= 360.0f) a -= 360.0f; while (a < 0) a += 360.0f; return a; }
static void ring(Ops& o, float rin, float rout, float a0, float sweep, uint32_t col) {
    if (sweep <= 0.2f) return;
    if (sweep > 359.0f) sweep = 359.0f;
    o.add(gfx_arc(C / 2.0f, C / 2.0f, rin, rout, wrap360(a0), wrap360(a0 + sweep), col));
}

struct Drive {                       // fake vehicle values for the gauges and the speed shown in gauge view
    float t = 12.0f;
    float speed_kph() const { return 72.0f + 46.0f * std::sin(t * 0.35f); }
    float rpm() const { return 2900.0f + 1500.0f * std::sin(t * 0.7f + 1.0f); }
};

// What the centre screen shows. The map is a placeholder for the CarPlay / Android Auto surface.
static void draw_centre(Ops& o, const Ui& ui, const Drive& dv, float long_p, int map_phase, bool phone) {
    const Model& m = ui.model();
    const float cx = C / 2.0f, cy = C / 2.0f;
    o.add(gfx_disc(cx, cy, 240, COL_BEZEL));
    o.add(gfx_disc(cx, cy, 236, 0x000000));
    if (ui.screen() == Screen::Home) {
        if (phone && !ui.gauge_view()) {
            // map surface in the chosen shape
            float w = 472, h = 472, r = 236;
            if (m.map_shape == 1) { w = h = 336; r = 10; }
            if (m.map_shape == 2) { w = 372; h = 279; r = 10; }
            if (m.map_shape == 3) { w = 418; h = 235; r = 10; }
            o.add(m.map_shape == 0 ? gfx_disc(cx, cy, 234, COL_MAP) : gfx_rrect(cx, cy, w, h, r, 0, COL_MAP));
            float s = float(map_phase % 120) / 120.0f * 40.0f;   // roads slide so it feels alive
            o.add(gfx_capsule(cx - 110, cy - 30 + s, cx + 110, cy - 30 + s, 12, COL_ROAD));
            o.add(gfx_capsule(cx - 110, cy + 50 + s * 0.5f, cx + 110, cy + 50 + s * 0.5f, 10, COL_ROAD));
            o.add(gfx_capsule(cx - 40, cy - 80, cx - 40, cy + 80, 12, COL_ROAD));
            o.add(gfx_capsule(cx + 50, cy - 80, cx + 50, cy + 80, 10, COL_ROAD));
            o.add(gfx_capsule(cx - 40, cy + 80, cx - 40, cy - 20, 6, COL_ACC));
            o.add(gfx_capsule(cx - 40, cy - 20, cx + 50, cy - 20, 6, COL_ACC));
            o.add(gfx_disc(cx - 40, cy + 40, 12, COL_TEXT));
            o.add(gfx_disc(cx - 40, cy + 40, 7, COL_ACC));
            float base = m.map_shape == 3 ? 100.0f : 118.0f;
            o.text(&FONT_SMALL, "CarPlay (phone)  12 min  3.4 mi", int(cx), int(cy + base) , TEXT_CENTER, COL_DIM);
        } else {
            if (!phone && m.no_phone_home) { o.text(&FONT_MED, "Home", int(cx), int(cy + 10), TEXT_CENTER, COL_TEXT); goto hint; }
            float mph = dv.speed_kph() * (m.imperial ? 0.621371f : 1.0f);
            float frac = mph / (m.imperial ? 120.0f : 200.0f);
            if (frac > 1) frac = 1;
            ring(o, 206, 220, 135, 270, COL_RING);
            o.add(gfx_arc_gradient(cx, cy, 206, 220, 135, 270, 270 * frac, 0x35A7FF, 0xFF5A4E));
            char b[16];
            snprintf(b, sizeof b, "%d", int(mph + 0.5f));
            o.text(&FONT_BIG, b, int(cx), int(cy + 24), TEXT_CENTER, COL_TEXT);
            o.text(&FONT_MED, m.imperial ? "MPH" : "KM/H", int(cx), int(cy + 74), TEXT_CENTER, COL_DIM);
            o.text(&FONT_SMALL, phone ? "Gauge view" : (m.no_phone_home ? "Home (no phone)" : "No phone"), int(cx), int(cy + 140), TEXT_CENTER, COL_DIM);
        }
    hint:
        o.text(&FONT_SMALL, phone ? "click: map / gauge    hold: settings" : "hold: settings   (P: phone on)", int(cx), 436, TEXT_CENTER, COL_DIM);
    } else if (ui.screen() == Screen::Settings) {
        o.text(&FONT_SMALL, "SETTINGS", int(cx), 74, TEXT_CENTER, COL_DIM);
        int sel = int(ui.row());
        for (int k = -2; k <= 2; k++) {
            int idx = ((sel + k) % kRows + kRows) % kRows;
            Row r = Row(idx);
            float y = cy + 4 + k * 54.0f;
            uint32_t col = k == 0 ? COL_TEXT : (k == 1 || k == -1 ? COL_DIM : 0x56606E);
            if (k == 0) {
                o.add(gfx_rrect(cx, y, 392, 50, 16, 0, COL_SEL));
                o.add(gfx_rrect(cx, y, 392, 50, 16, 2, COL_ACC));
            }
            const font_t* f = k == 0 ? &FONT_MED : &FONT_SMALL;
            o.text(f, label(r), int(cx) - 168, int(y) + (k == 0 ? 9 : 5), TEXT_LEFT, col);
            std::string v = value(m, r);
            if (!v.empty()) o.text(f, v, int(cx) + 168, int(y) + (k == 0 ? 9 : 5), TEXT_RIGHT, k == 0 ? COL_ACC : col);
        }
        o.text(&FONT_SMALL, "turn: move   click: edit   hold: back", int(cx), 436, TEXT_CENTER, COL_DIM);
    } else {
        Row r = ui.row();
        o.text(&FONT_SMALL, label(r), int(cx), 120, TEXT_CENTER, COL_DIM);
        if (r == Row::Brightness) {
            ring(o, 196, 210, 135, 270, COL_RING);
            ring(o, 196, 210, 135, 270.0f * float(m.brightness) / 100.0f, COL_ACC);
            char b[16];
            snprintf(b, sizeof b, "%d", m.brightness);
            o.text(&FONT_BIG, b, int(cx), int(cy + 24), TEXT_CENTER, COL_TEXT);
            o.text(&FONT_MED, "%", int(cx), int(cy + 70), TEXT_CENTER, COL_DIM);
        } else {
            o.text(&FONT_MED, value(m, r), int(cx), int(cy + 10), TEXT_CENTER, COL_TEXT);
            if (r == Row::Theme && phone && m.match_carplay)
                o.text(&FONT_SMALL, "CarPlay is open: small screens use the Apple look", int(cx), int(cy + 60), TEXT_CENTER, COL_DIM);
            for (int s = -1; s <= 1; s += 2) {          // chevrons: this value can be turned either way
                float x = cx + s * 190.0f;
                o.add(gfx_capsule(x - s * 6, cy - 14, x + s * 6, cy, 4, COL_ACC));
                o.add(gfx_capsule(x - s * 6, cy + 14, x + s * 6, cy, 4, COL_ACC));
            }
        }
        o.text(&FONT_SMALL, "turn: change   click: keep   hold: cancel", int(cx), 436, TEXT_CENTER, COL_DIM);
    }
    if (long_p > 0.02f) ring(o, 226, 234, -90, 360.0f * long_p, COL_ACC);
}

// ---------------------------------------------------------------- the rig: small screens + dial + centre
struct Rig {
    mock_t* mock;
    Ui ui;
    ClickDetector det;
    Drive drive;
    Model applied;
    bool applied_valid = false;
    int map_phase = 0;
    std::string last_event = "-";
    bool dirty = true, frozen = false;       // frozen: the fake drive stands still (scripted pictures)
    int ticks = 0;
    uint32_t now = 0;                      // milliseconds, from the main loop (real or scripted)
    uint32_t pending_key_up = 0;           // time of a Space/Enter release waiting out X11 auto-repeat
    bool key_up_pending = false, key_down = false;

    bool phone = true;                       // a phone is showing CarPlay (key P toggles it)
    int shown_theme = -1;                    // what the small screens are set to
    theme_t theme_of(const Model& m) const { int t = effective_theme(m, phone); return t == 0 ? THEME_CLASSIC : t == 1 ? THEME_MODERN : THEME_CARPLAY; }

    void init(mock_t* mk, const Model& start) {
        mock = mk;
        mock_init(mock);
        ui.mutable_model() = start;
        applied = start;
        applied_valid = true;
        aux_display_init(mock_hal(mock), theme_of(start), start.imperial);
        shown_theme = int(theme_of(start));
    }

    void apply_model() {
        const Model& m = ui.model();
        if (!applied_valid || int(theme_of(m)) != shown_theme) { aux_display_set_theme(theme_of(m)); shown_theme = int(theme_of(m)); }
        if (!applied_valid || m.imperial != applied.imperial) aux_display_set_imperial(m.imperial);
        applied = m;
        applied_valid = true;
    }

    static const char* input_name(Input in) {
        switch (in) {
            case Input::TurnLeft: return "turn left";
            case Input::TurnRight: return "turn right";
            case Input::Click: return "click";
            default: return "long press";
        }
    }
    static const char* screen_name(Screen s) { return s == Screen::Home ? "Home" : s == Screen::Settings ? "Settings" : "Edit"; }

    void dispatch(Input in) {
        ui.handle(in);
        apply_model();
        if (ui.take_committed()) save();
        char b[160];
        snprintf(b, sizeof b, "%s -> %s%s%s", input_name(in), screen_name(ui.screen()),
                 ui.screen() == Screen::Home ? (ui.gauge_view() ? " (gauge)" : " (maps)") : ": ",
                 ui.screen() == Screen::Home ? "" : label(ui.row()));
        last_event = b;
        printf("input: %s\n", b);
        dirty = true;
    }

    // One firmware tick (10 ms): feed the four screens and send what changed, within the bus budget.
    void tick() {
        ticks++;
        if (!frozen) drive.t += 0.01f;
        screen_values_t v;
        auto ok = [](float x) { chosen_t c; c.value = x; c.valid = true; c.src = SRC_LOCAL; return c; };
        v.speed_kph = ok(drive.speed_kph());
        v.rpm = ok(drive.rpm());
        v.battery_v = ok(13.8f);
        v.fuel_pct = ok(62.0f);
        v.coolant_c = ok(90.0f);
        v.oil_kpa = ok(350.0f);
        const screen_cfg_t* layout = screens_layout(theme_of(ui.model()));
        for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
            screen_view_t view = screens_build(&layout[s], &v, ui.model().imperial);
            aux_display_screen(s, &view);
        }
        aux_display_poll_budget(AUX_POLL_RUNS, AUX_POLL_BYTES);
        if (ticks % 4 == 0) { map_phase++; if (!ui.gauge_view() && ui.screen() == Screen::Home) dirty = true; }
        if (ui.gauge_view() && ui.screen() == Screen::Home && ticks % 8 == 0) dirty = true;
    }

    std::string path = "hmi_settings.txt";
    void save() const {
        FILE* f = fopen(path.c_str(), "w");
        if (!f) return;
        const Model& m = ui.model();
        fprintf(f, "theme=%d\nmatch_carplay=%d\nimperial=%d\nno_phone_home=%d\nmap_shape=%d\nbrightness=%d\n", m.theme, m.match_carplay, m.imperial, m.no_phone_home, m.map_shape, m.brightness);
        fclose(f);
    }
    static Model load(const std::string& p) {
        Model m;
        FILE* f = fopen(p.c_str(), "r");
        if (!f) return m;
        char line[64];
        while (fgets(line, sizeof line, f)) {
            int v;
            if (sscanf(line, "theme=%d", &v) == 1 && v >= 0 && v <= 2) m.theme = v;
            if (sscanf(line, "match_carplay=%d", &v) == 1) m.match_carplay = v != 0;
            if (sscanf(line, "imperial=%d", &v) == 1) m.imperial = v != 0;
            if (sscanf(line, "no_phone_home=%d", &v) == 1) m.no_phone_home = v != 0;
            if (sscanf(line, "map_shape=%d", &v) == 1 && v >= 0 && v <= 3) m.map_shape = v;
            if (sscanf(line, "brightness=%d", &v) == 1 && v >= 10 && v <= 100) m.brightness = v;
        }
        fclose(f);
        return m;
    }
};

static uint32_t rgb565_to_rgb(uint16_t p) {
    uint32_t r = ((p >> 11) & 31) * 255 / 31, g = ((p >> 5) & 63) * 255 / 63, b = (p & 31) * 255 / 31;
    return (r << 16) | (g << 8) | b;
}
static uint32_t scale_rgb(uint32_t c, int pct) {
    uint32_t r = ((c >> 16) & 255) * uint32_t(pct) / 100, g = ((c >> 8) & 255) * uint32_t(pct) / 100, b = (c & 255) * uint32_t(pct) / 100;
    return (r << 16) | (g << 8) | b;
}

// Compose the whole window: centre screen (dimmed by the brightness setting), 2x2 small screens, HUD strip.
static void compose(Rig& r, std::vector<uint32_t>& win, const char* hud2, bool redraw_centre = true) {
    win.assign(size_t(WIN_W) * WIN_H, 0x0B0D10);
    static std::vector<uint32_t> centre_rgb;               // the centre picture is only re-rendered when it changed
    if (redraw_centre || centre_rgb.empty()) {
        static Ops ops;
        ops.n = 0; ops.dropped = 0;
        draw_centre(ops, r.ui, r.drive, r.det.long_progress(r.now), r.map_phase, r.phone);
        static std::vector<uint16_t> c565;
        c565.assign(size_t(C) * C, 0);
        gfx_render(ops.v, ops.n, 0, 0, C, C, c565.data(), C);
        int pct = r.ui.model().brightness;
        centre_rgb.resize(size_t(C) * C);
        for (size_t i = 0; i < centre_rgb.size(); i++) centre_rgb[i] = scale_rgb(rgb565_to_rgb(c565[i]), pct);
    }
    for (int y = 0; y < C; y++) memcpy(&win[size_t(y) * WIN_W], &centre_rgb[size_t(y) * C], size_t(C) * 4);
    for (int s = 0; s < 4; s++) {
        int ox = C + GAP + (s % 2) * SM, oy = (s / 2) * SM;
        for (int y = 0; y < SM; y++)
            for (int x = 0; x < SM; x++) {
                int dx = x - 120, dy = y - 120;
                if (dx * dx + dy * dy > 120 * 120) continue;
                win[size_t(oy + y) * WIN_W + ox + x] = rgb565_to_rgb(r.mock->fb[s][y * SM + x]);
            }
    }
    // HUD strip
    Ops h;
    h.text(&FONT_SMALL, "dial:  wheel = turn   left button / Space = click   hold 0.6 s = long press   P = phone   Q = quit", 12, 20, TEXT_LEFT, COL_DIM);
    h.text(&FONT_SMALL, std::string("last: ") + r.last_event + (hud2 ? hud2 : ""), 12, 38, TEXT_LEFT, COL_TEXT);
    std::vector<uint16_t> s565(size_t(WIN_W) * HUD_H, 0);
    gfx_render(h.v, h.n, 0, 0, WIN_W, HUD_H, s565.data(), WIN_W);
    for (int y = 0; y < HUD_H; y++)
        for (int x = 0; x < WIN_W; x++) win[size_t(C + y) * WIN_W + x] = rgb565_to_rgb(s565[size_t(y) * WIN_W + x]);
}

// ---------------------------------------------------------------- run loops
static uint32_t real_ms() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return uint32_t(ts.tv_sec) * 1000u + uint32_t(ts.tv_nsec / 1000000);
}

// Let the small screens catch up with a frozen drive (also outlasts the modern theme's number hold-off).
static void settle(Rig& r) {
    for (int round = 0; round < 3; round++) {
        for (int i = 0; i < AUX_TEXT_HOLD_TICKS + 3; i++) { r.now += 10; r.tick(); }
        int guard = 0;
        while (aux_display_pending_tiles() > 0 && guard++ < 5000) { r.now += 10; r.tick(); }
    }
}

static void press_click(Rig& r) {
    Input in;
    r.det.press(r.now);
    r.now += 80;
    if (r.det.release(r.now, &in)) r.dispatch(in);
}
static void press_hold(Rig& r) {
    Input in;
    r.det.press(r.now);
    r.now += ClickDetector::kLongMs + 50;
    if (r.det.tick(r.now, &in)) r.dispatch(in);
    r.now += 100;
    if (r.det.release(r.now, &in)) r.dispatch(in);           // after a long press the release must do nothing
}

static int run_script(Rig& r, const std::string& script) {
    std::string tok;
    int shots = 0;
    for (size_t i = 0; i <= script.size(); i++) {
        char ch = i < script.size() ? script[i] : ',';
        if (ch != ',' && ch != ' ') { tok += ch; continue; }
        if (tok.empty()) continue;
        if (tok == "R") r.dispatch(Input::TurnRight);
        else if (tok == "L") r.dispatch(Input::TurnLeft);
        else if (tok == "C") press_click(r);
        else if (tok == "H") press_hold(r);
        else if (tok == "P") { r.phone = !r.phone; r.apply_model(); r.dirty = true; }
        else if (tok.rfind("shot=", 0) == 0) {
            settle(r);
            std::vector<uint32_t> win;
            compose(r, win, nullptr);
            std::string p = tok.substr(5);
            if (!write_png(p.c_str(), win, WIN_W, WIN_H)) { printf("cannot write %s\n", p.c_str()); return 1; }
            printf("wrote %s\n", p.c_str());
            shots++;
        } else { printf("unknown script token '%s'\n", tok.c_str()); return 1; }
        tok.clear();
    }
    if (mock_errors(r.mock)) { printf("panel protocol errors: %d\n", mock_errors(r.mock)); return 1; }
    (void)shots;
    return 0;
}

static int g_fail = 0;
#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s (line %d)\n", msg, __LINE__); g_fail++; } } while (0)

static uint32_t fb_sum(const mock_t& m) {
    uint32_t h = 2166136261u;
    for (int s = 0; s < 4; s++)
        for (int i = 0; i < 240 * 240; i++) h = (h ^ m.fb[s][i]) * 16777619u;
    return h;
}

static int run_selftest() {
    // 1. push-button -> click / long press
    {
        ClickDetector d;
        Input in = Input::TurnLeft;
        d.press(1000);
        CHECK(!d.tick(1599, &in), "no long press before 600 ms");
        CHECK(d.tick(1600, &in) && in == Input::LongPress, "long press fires at 600 ms while still held");
        CHECK(!d.tick(2500, &in), "long press fires once");
        CHECK(!d.release(2600, &in), "release after a long press is silent");
        d.press(5000);
        CHECK(d.release(5100, &in) && in == Input::Click, "short press clicks on release");
        d.press(7000);
        CHECK(d.long_progress(7300) > 0.45f && d.long_progress(7300) < 0.55f, "progress halfway");
        CHECK(!d.release(7000 + 599, &in) || in == Input::Click, "599 ms is still a click");
    }
    // 2. menu flow
    {
        Ui ui;
        CHECK(ui.screen() == Screen::Home && !ui.gauge_view(), "starts on Home, maps");
        ui.handle(Input::TurnRight);
        CHECK(ui.screen() == Screen::Home, "turning on Home does nothing");
        ui.handle(Input::Click);
        CHECK(ui.gauge_view(), "click on Home flips to gauge");
        ui.handle(Input::Click);
        CHECK(!ui.gauge_view(), "and back to maps");
        ui.handle(Input::LongPress);
        CHECK(ui.screen() == Screen::Settings && ui.row() == Row::Theme, "long press opens Settings at the first row");
        ui.handle(Input::TurnLeft);
        CHECK(ui.row() == Row::Back, "turning left from the first row wraps to Back");
        ui.handle(Input::TurnRight);
        ui.handle(Input::TurnRight);
        ui.handle(Input::TurnRight);
        CHECK(ui.row() == Row::Units, "three steps right from Back = Units");
        ui.handle(Input::TurnRight);
        CHECK(ui.row() == Row::NoPhone, "one more = No phone shows");
        ui.handle(Input::Click);
        CHECK(ui.screen() == Screen::Edit, "click edits");
        ui.handle(Input::TurnRight);
        CHECK(ui.model().no_phone_home, "turn changes the value live");
        ui.handle(Input::Click);
        CHECK(ui.screen() == Screen::Settings && ui.take_committed() && !ui.take_committed(), "click keeps; committed reported once");
        ui.handle(Input::Click);
        ui.handle(Input::TurnLeft);
        CHECK(!ui.model().no_phone_home, "edited back");
        ui.handle(Input::LongPress);
        CHECK(ui.screen() == Screen::Settings && ui.model().no_phone_home && !ui.take_committed(), "long press cancels and restores");
        ui.handle(Input::Click);
        ui.handle(Input::Click);
        CHECK(!ui.take_committed(), "keeping an unchanged value is not a change");
        ui.handle(Input::LongPress);
        CHECK(ui.screen() == Screen::Home, "long press in the list goes back to Home");
        // Back row and the value ranges
        ui.handle(Input::LongPress);
        for (int i = 0; i < kRows - 1; i++) ui.handle(Input::TurnRight);
        CHECK(ui.row() == Row::Back, "last row is Back");
        ui.handle(Input::Click);
        CHECK(ui.screen() == Screen::Home, "Back returns Home");
        ui.handle(Input::LongPress);
        for (int i = 0; i < 5; i++) ui.handle(Input::TurnRight);
        CHECK(ui.row() == Row::Brightness, "Brightness row");
        ui.handle(Input::Click);
        for (int i = 0; i < 30; i++) ui.handle(Input::TurnRight);
        CHECK(ui.model().brightness == 100, "brightness stops at 100");
        for (int i = 0; i < 30; i++) ui.handle(Input::TurnLeft);
        CHECK(ui.model().brightness == 10, "and at 10");
        ui.handle(Input::LongPress);
        ui.handle(Input::TurnLeft);
        ui.handle(Input::TurnLeft);
        CHECK(ui.row() == Row::NoPhone, "back in the list, two rows up");
        ui.handle(Input::TurnRight);
        ui.handle(Input::Click);
        for (int i = 0; i < 5; i++) ui.handle(Input::TurnRight);
        CHECK(ui.model().map_shape == 1, "map shape wraps through four values");
    }
    // 3. every screen draws something and fits the op list
    {
        static Ops ops;
        static std::vector<uint16_t> px;
        px.assign(size_t(C) * C, 0);
        Drive dv;
        for (int state = 0; state < 2 + kRows + 6; state++) {
            Ui ui;
            if (state == 1) ui.handle(Input::Click);
            if (state >= 2) {
                ui.handle(Input::LongPress);
                int rowi = state - 2;
                if (rowi >= kRows) rowi = rowi - kRows;           // second pass: edit each editable row
                for (int i = 0; i < rowi; i++) ui.handle(Input::TurnRight);
                if (state >= 2 + kRows) ui.handle(Input::Click);
            }
            for (int shape = 0; shape < (state == 0 ? 4 : 1); shape++) {
                ui.mutable_model().map_shape = shape;
                ops.n = 0; ops.dropped = 0;
                draw_centre(ops, ui, dv, 0.5f, 3, true);
                char msg[80];
                snprintf(msg, sizeof msg, "state %d shape %d fits the op list (%d ops)", state, shape, ops.n);
                CHECK(ops.dropped == 0, msg);
                std::fill(px.begin(), px.end(), uint16_t(0));
                gfx_render(ops.v, ops.n, 0, 0, C, C, px.data(), C);
                int lit = 0;
                for (uint16_t p : px) lit += p != 0;
                snprintf(msg, sizeof msg, "state %d shape %d draws something (%d pixels)", state, shape, lit);
                CHECK(lit > 4000, msg);
            }
        }
    }
    // 4. a committed theme or unit change reaches the real small-screen code, without protocol errors
    {
        static mock_t mock;
        Rig r;
        r.path = "build/hmi_selftest_settings.txt";
        Model m;
        m.theme = 1;
        r.init(&mock, m);
        r.frozen = true;
        r.phone = false;                       // no CarPlay: the owner's own theme shows
        r.apply_model();
        settle(r);
        uint32_t modern = fb_sum(mock);
        CHECK(modern != 2166136261u, "small screens drew");
        r.dispatch(Input::LongPress);          // Settings, Theme
        r.dispatch(Input::Click);              // edit
        r.dispatch(Input::TurnLeft);           // modern -> classic, live
        settle(r);
        uint32_t classic = fb_sum(mock);
        CHECK(classic != modern, "turning the theme changes the small screens at once");
        r.dispatch(Input::LongPress);          // cancel
        settle(r);
        CHECK(fb_sum(mock) == modern, "cancelling restores the small screens exactly");
        r.dispatch(Input::Click);
        r.dispatch(Input::TurnLeft);
        r.dispatch(Input::Click);              // keep classic
        settle(r);
        CHECK(fb_sum(mock) == classic, "keeping the change leaves classic on the screens");
        // CarPlay open: the Apple look, whatever the owner chose, unless "With CarPlay" is off
        r.phone = true;
        r.apply_model();
        settle(r);
        uint32_t apple = fb_sum(mock);
        CHECK(apple != classic && apple != modern, "CarPlay open shows the Apple look");
        r.ui.mutable_model().match_carplay = false;
        r.apply_model();
        settle(r);
        CHECK(fb_sum(mock) == classic, "with the option off CarPlay does not change the screens");
        r.ui.mutable_model().match_carplay = true;
        r.phone = false;
        r.apply_model();
        settle(r);
        CHECK(fb_sum(mock) == classic, "closing CarPlay returns to the owner's theme");
        // saved settings round trip
        Model back = Rig::load(r.path);
        CHECK(back == r.ui.model(), "saved settings load back identical");
        CHECK(mock_errors(&mock) == 0, "no panel protocol errors through all of that");
    }
    printf(g_fail ? "hmi_sim selftest: %d FAILED\n" : "hmi_sim selftest: all passed\n", g_fail);
    return g_fail ? 1 : 0;
}

static int run_window(Rig& r) {
    x11win_t* win = x11_open(WIN_W, WIN_H, "Dial HMI simulator (proof of concept)");
    if (!win) { printf("no display (X11)\n"); return 1; }
    uint32_t t0 = real_ms(), last_tick = 0, last_draw = 0;
    bool running = true;
    std::vector<uint32_t> img;
    while (running) {
        r.now = real_ms() - t0;
        hev_t e;
        while (x11_poll(win, &e)) {
            Input in;
            switch (e.type) {
                case HEV_QUIT: running = false; break;
                case HEV_KEY:
                    if (e.key == 'q') running = false;
                    else if (e.key == 'p') { r.phone = !r.phone; r.apply_model(); r.dirty = true; }
                    else if (e.key == HK_RIGHT || e.key == HK_UP || e.key == 'd') r.dispatch(Input::TurnRight);
                    else if (e.key == HK_LEFT || e.key == HK_DOWN || e.key == 'a') r.dispatch(Input::TurnLeft);
                    else if (e.key == HK_ESC) r.dispatch(Input::LongPress);
                    else if (e.key == ' ' || e.key == HK_ENTER) {
                        if (r.key_up_pending) r.key_up_pending = false;      // auto-repeat: release + press pair
                        else if (!r.det.held()) { r.det.press(r.now); r.dirty = true; }
                    }
                    break;
                case HEV_KEY_UP:
                    if (e.key == ' ' || e.key == HK_ENTER) { r.key_up_pending = true; r.pending_key_up = r.now; }
                    break;
                case HEV_WHEEL: r.dispatch(e.key > 0 ? Input::TurnRight : Input::TurnLeft); break;
                case HEV_MOUSE_DOWN:
                    if (e.key == 1 && !r.det.held()) { r.det.press(r.now); r.dirty = true; }
                    break;
                case HEV_MOUSE_UP:
                    if (e.key == 1 && r.det.release(r.now, &in)) r.dispatch(in);
                    r.dirty = true;
                    break;
                default: break;
            }
        }
        Input in;
        if (r.key_up_pending && r.now - r.pending_key_up >= 30) {
            r.key_up_pending = false;
            if (r.det.release(r.now, &in)) r.dispatch(in);
            r.dirty = true;
        }
        if (r.det.tick(r.now, &in)) r.dispatch(in);                           // long press fires while held
        while (last_tick + 10 <= r.now) { r.tick(); last_tick += 10; }
        if (r.now - last_draw >= 33) {
            bool centre = r.dirty || r.det.held();
            compose(r, img, nullptr, centre);
            x11_present(win, img.data(), WIN_W, WIN_H);
            r.dirty = false;
            last_draw = r.now;
        }
        struct timespec ts = { 0, 2 * 1000 * 1000 };
        nanosleep(&ts, nullptr);
    }
    x11_close(win);
    return 0;
}

int main(int argc, char** argv) {
    std::string script, settings = "hmi_settings.txt";
    bool selftest = false, fresh = false, headless = false;
    (void)headless;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--selftest")) selftest = true;
        else if (!strcmp(argv[i], "--fresh")) fresh = true;
        else if (!strcmp(argv[i], "--headless")) headless = true;
        else if (!strcmp(argv[i], "--script") && i + 1 < argc) script = argv[++i];
        else if (!strcmp(argv[i], "--settings") && i + 1 < argc) settings = argv[++i];
        else {
            printf("usage: hmi_sim [--selftest] [--script \"H,R,C,shot=a.png\"] [--fresh] [--settings file] [--headless]\n");
            return 2;
        }
    }
    if (selftest) return run_selftest();
    static mock_t mock;
    Rig r;
    r.path = script.empty() ? settings : std::string("build/hmi_script_settings.txt");
    r.init(&mock, fresh || !script.empty() ? Model() : Rig::load(settings));
    if (!script.empty()) {
        r.frozen = true;
        return run_script(r, script);
    }
    return run_window(r);
}
