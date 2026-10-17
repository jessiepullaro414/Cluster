// clusterd: the Linux option's glue between display/'s hardware, the private CAN link and LIVI.
//
//   private CAN link (SocketCAN) --> vhal::Bridge --> LIVI telemetry (POST :4000/telemetry), every 100 ms
//   Shell state --> DisplaySettings, SpeedCalibration, InputConfig, TripCommand, heartbeat --> gauges/
//   dial: ADC angle (sysfs IIO) + click (evdev, a gpio-keys node) --> Shell --> uinput keys / LIVI page
//   LIVI state/status.json --> which phone is projecting
//   PowerState suspend request --> save, heartbeat "suspending", suspend_cmd, rezero the dial on resume
//   GET :4010/ and /state --> the settings page LIVI shows as its custom page
//
// Every piece of logic is in the pure files (shell.h, dial_angle, link_tx, telemetry, state_io) and
// host-tested; this file is only I/O. Bench use without hardware: --can none --dial-stdin, keys
// a/d turn, c click, h hold 0.7 s, m hold 1.6 s, q quit.
#include <fcntl.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <termios.h>
#include <arpa/inet.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "bridge.h"
#include "dial_angle.h"
#include "link_tx.h"
#include "shell.h"
#include "state_io.h"
#include "telemetry.h"

using namespace clusterd;

static uint32_t now_ms() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return uint32_t(uint64_t(ts.tv_sec) * 1000u + uint64_t(ts.tv_nsec) / 1000000u);
}

// CLOCK_BOOTTIME keeps counting in suspend; a jump against CLOCK_MONOTONIC means we were asleep.
static int64_t boottime_minus_mono_ms() {
    timespec b, m;
    clock_gettime(CLOCK_BOOTTIME, &b);
    clock_gettime(CLOCK_MONOTONIC, &m);
    return (int64_t(b.tv_sec) - m.tv_sec) * 1000 + (int64_t(b.tv_nsec) - m.tv_nsec) / 1000000;
}

static std::string read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return "";
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static bool write_file_atomic(const std::string& path, const std::string& text) {
    std::string tmp = path + ".tmp";
    {
        std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
        if (!f) return false;
        f << text;
        if (!f.flush()) return false;
    }
    return std::rename(tmp.c_str(), path.c_str()) == 0;
}

// ---- SocketCAN ---------------------------------------------------------------------------------

static int can_open(const std::string& ifname) {
    if (ifname == "none") return -1;
    int s = socket(PF_CAN, SOCK_RAW | SOCK_NONBLOCK, CAN_RAW);
    if (s < 0) { std::perror("clusterd: CAN socket"); return -1; }
    ifreq ifr = {};
    std::snprintf(ifr.ifr_name, IFNAMSIZ, "%s", ifname.c_str());
    if (ioctl(s, SIOCGIFINDEX, &ifr) < 0) { std::fprintf(stderr, "clusterd: no CAN interface %s\n", ifname.c_str()); close(s); return -1; }
    sockaddr_can addr = {};
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;
    if (bind(s, reinterpret_cast<sockaddr*>(&addr), sizeof addr) < 0) { std::perror("clusterd: CAN bind"); close(s); return -1; }
    return s;
}

static void can_send(int s, const Frame& f) {
    if (s < 0) return;
    can_frame cf = {};
    cf.can_id = f.id;
    cf.can_dlc = 8;
    std::memcpy(cf.data, f.data, 8);
    if (write(s, &cf, sizeof cf) != ssize_t(sizeof cf) && errno != EAGAIN && errno != ENOBUFS)
        std::perror("clusterd: CAN write");
}

// ---- uinput: the dial's keys for LIVI and the phone ------------------------------------------
// LIVI key bindings to set (livi_config.py does): knobLeft F13, knobRight F14, selectDown Enter, back Backspace.

static int uinput_open() {
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) { std::perror("clusterd: /dev/uinput (dial keys disabled)"); return -1; }
    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    for (int k : {KEY_F13, KEY_F14, KEY_ENTER, KEY_BACKSPACE}) ioctl(fd, UI_SET_KEYBIT, k);
    uinput_setup us = {};
    us.id.bustype = BUS_VIRTUAL;
    us.id.vendor = 0x1d6b;   // Linux Foundation: a virtual device, not real hardware
    us.id.product = 0x0104;
    std::snprintf(us.name, UINPUT_MAX_NAME_SIZE, "cluster dial");
    if (ioctl(fd, UI_DEV_SETUP, &us) < 0 || ioctl(fd, UI_DEV_CREATE) < 0) { std::perror("clusterd: uinput setup"); close(fd); return -1; }
    return fd;
}

static void uinput_emit(int fd, int type, int code, int value) {
    input_event ev = {};
    ev.type = uint16_t(type);
    ev.code = uint16_t(code);
    ev.value = value;
    if (write(fd, &ev, sizeof ev) < 0) std::perror("clusterd: uinput write");
}

static void send_key(int fd, Key k) {
    int code = k == Key::KnobLeft ? KEY_F13 : k == Key::KnobRight ? KEY_F14 : k == Key::Select ? KEY_ENTER : KEY_BACKSPACE;
    std::printf("clusterd: key %s\n", k == Key::KnobLeft ? "knobLeft" : k == Key::KnobRight ? "knobRight" : k == Key::Select ? "select" : "back");
    if (fd < 0) return;
    uinput_emit(fd, EV_KEY, code, 1);
    uinput_emit(fd, EV_SYN, SYN_REPORT, 0);
    uinput_emit(fd, EV_KEY, code, 0);
    uinput_emit(fd, EV_SYN, SYN_REPORT, 0);
}

// ---- HTTP: push to LIVI, serve the settings page --------------------------------------------

static bool http_post_json(const std::string& host, int port, const char* path, const std::string& body) {
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return false;
    timeval tv = {0, 100000};
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    sockaddr_in a = {};
    a.sin_family = AF_INET;
    a.sin_port = htons(uint16_t(port));
    inet_pton(AF_INET, host.c_str(), &a.sin_addr);
    bool ok = false;
    if (connect(s, reinterpret_cast<sockaddr*>(&a), sizeof a) == 0) {
        std::string req = std::string("POST ") + path + " HTTP/1.1\r\nHost: " + host + "\r\nContent-Type: application/json\r\n" +
                          "Content-Length: " + std::to_string(body.size()) + "\r\nConnection: close\r\n\r\n" + body;
        ok = write(s, req.data(), req.size()) == ssize_t(req.size());
        char buf[64];
        ssize_t n = read(s, buf, sizeof buf - 1);   // "HTTP/1.1 204"
        ok = ok && n > 12 && std::strncmp(buf + 9, "204", 3) == 0;
    }
    close(s);
    return ok;
}

static int http_listen(int port) {
    int s = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    sockaddr_in a = {};
    a.sin_family = AF_INET;
    a.sin_port = htons(uint16_t(port));
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);   // LIVI on the same machine only
    if (bind(s, reinterpret_cast<sockaddr*>(&a), sizeof a) < 0 || listen(s, 8) < 0) {
        std::perror("clusterd: settings page port");
        close(s);
        return -1;
    }
    return s;
}

static void http_serve_one(int ls, const std::string& web_dir, const Shell& sh, const vhal::Bridge& b, uint32_t now) {
    int c = accept(ls, nullptr, nullptr);
    if (c < 0) return;
    timeval tv = {0, 200000};
    setsockopt(c, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    char buf[1024];
    ssize_t n = read(c, buf, sizeof buf - 1);
    if (n > 0) {
        buf[n] = 0;
        std::string body, type = "text/html; charset=utf-8", status = "200 OK";
        if (std::strncmp(buf, "GET /state", 10) == 0) { body = page_state_json(sh, b, now); type = "application/json"; }
        else if (std::strncmp(buf, "GET / ", 6) == 0 || std::strncmp(buf, "GET /index.html", 15) == 0) {
            body = read_file(web_dir + "/centre.html");
            if (body.empty()) {
                std::fprintf(stderr, "clusterd: no %s/centre.html (check --web)\n", web_dir.c_str());
                status = "404 Not Found";
            }
        } else status = "404 Not Found";
        std::string head = "HTTP/1.1 " + status + "\r\nContent-Type: " + type + "\r\nContent-Length: " + std::to_string(body.size()) +
                           "\r\nCache-Control: no-store\r\nCross-Origin-Resource-Policy: cross-origin\r\nConnection: close\r\n\r\n";
        std::string all = head + body;
        if (write(c, all.data(), all.size()) < 0) std::perror("clusterd: page write");
    }
    close(c);
}

// ---- main ----------------------------------------------------------------------------------------

struct Args {
    std::string config = "/etc/clusterd.conf";
    std::string settings = "/var/lib/clusterd/settings.conf";
    std::string web = "/usr/share/clusterd/web";
    std::string livi_status;          // default: $HOME/.config/LIVI/state/status.json
    std::string adc;                  // e.g. /sys/bus/iio/devices/iio:device0/in_voltage1_raw
    std::string click;                // e.g. /dev/input/by-path/platform-gpio-keys-event
    std::string can_override;
    std::string replay;               // bench: a can_replay.py --dry-run log, played in a loop
    std::string harness;              // bench: HOST:PORT of gauges-fw's harness (the four small gauges), UDP
    bool dial_stdin = false;
};

struct ReplayFrame {
    uint32_t t_ms, id;
    uint8_t data[8], len;
};

static Args parse_args(int argc, char** argv) {
    Args a;
    const char* home = std::getenv("HOME");
    a.livi_status = std::string(home ? home : "/root") + "/.config/LIVI/state/status.json";
    for (int i = 1; i < argc; i++) {
        std::string k = argv[i];
        auto next = [&]() { return i + 1 < argc ? std::string(argv[++i]) : std::string(); };
        if (k == "--config") a.config = next();
        else if (k == "--settings") a.settings = next();
        else if (k == "--web") a.web = next();
        else if (k == "--livi-status") a.livi_status = next();
        else if (k == "--adc") a.adc = next();
        else if (k == "--click") a.click = next();
        else if (k == "--can") a.can_override = next();
        else if (k == "--dial-stdin") a.dial_stdin = true;
        else if (k == "--replay") a.replay = next();
        else if (k == "--harness-udp") a.harness = next();
        else { std::fprintf(stderr, "clusterd: unknown option %s\n", k.c_str()); std::exit(2); }
    }
    return a;
}

int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IOLBF, 0);   // one line at a time into journald or a log file
    Args args = parse_args(argc, argv);
    DialConfig dial_cfg;
    Config cfg;
    cfg.dial = &dial_cfg;
    parse_config(read_file(args.config), &cfg);
    parse_config(read_file(args.settings), &cfg);   // the dial's own changes win
    if (!args.can_override.empty()) cfg.can_if = args.can_override;

    vhal::Bridge bridge;
    Shell shell;
    shell.mutable_ui().mutable_model() = cfg.model;
    DialAngle dial(dial_cfg);
    LinkTx tx;
    PowerPolicy power;
    VehicleSetup vehicle = cfg.vehicle;
    tx.set_vehicle(vehicle);

    int can = can_open(cfg.can_if);
    int ui = uinput_open();
    int page = http_listen(cfg.page_port);
    int click = args.click.empty() ? -1 : open(args.click.c_str(), O_RDONLY | O_NONBLOCK);
    if (!args.click.empty() && click < 0) std::perror("clusterd: click input");
    termios saved_tio = {};
    bool tio = false;
    if (args.dial_stdin && isatty(0) && tcgetattr(0, &saved_tio) == 0) {
        termios raw = saved_tio;
        raw.c_lflag &= ~tcflag_t(ICANON | ECHO);
        tcsetattr(0, TCSANOW, &raw);
        tio = true;
    }

    auto push_path = [&](const char* p) {
        if (!p) return;
        std::printf("clusterd: page %s\n", p);
        if (!http_post_json(cfg.livi_url_host, cfg.livi_port, "/telemetry", path_json(p)))
            std::fprintf(stderr, "clusterd: LIVI did not take the page change (is it running?)\n");
    };
    auto act = [&](const Action& a) {
        if (a.key != Key::None) send_key(ui, a.key);
        push_path(a.path);
    };
    hmi::Model last_saved = cfg.model;
    auto save_if_committed = [&]() {
        if (!shell.mutable_ui().take_committed()) return;
        const hmi::Model& m = shell.ui().model();
        if (!write_file_atomic(args.settings, format_settings(m, vehicle))) std::perror("clusterd: saving settings");
        if (m.map_shape != last_saved.map_shape && !cfg.map_shape_cmd.empty()) {
            std::string cmd = cfg.map_shape_cmd + " " + std::to_string(m.map_shape);
            if (std::system(cmd.c_str()) != 0) std::fprintf(stderr, "clusterd: %s failed\n", cmd.c_str());
        }
        last_saved = m;
    };

    std::vector<ReplayFrame> replay;
    if (!args.replay.empty()) {
        std::istringstream lines(read_file(args.replay));
        std::string line;
        ReplayFrame f;
        while (std::getline(lines, line))
            if (parse_replay_line(line, &f.t_ms, &f.id, f.data, &f.len)) replay.push_back(f);
        std::printf("clusterd: replaying %zu frames from %s in a loop\n", replay.size(), args.replay.c_str());
    }
    // Bench: the four small gauges in gauges-fw's harness, fed the Android app's telemetry line.
    int harness_fd = -1;
    sockaddr_in harness_to = {};
    if (!args.harness.empty()) {
        size_t colon = args.harness.rfind(':');
        std::string host = colon == std::string::npos ? args.harness : args.harness.substr(0, colon);
        int port = colon == std::string::npos ? 5005 : std::atoi(args.harness.c_str() + colon + 1);
        harness_to.sin_family = AF_INET;
        harness_to.sin_port = htons(uint16_t(port));
        if (inet_pton(AF_INET, host.c_str(), &harness_to.sin_addr) == 1) harness_fd = socket(AF_INET, SOCK_DGRAM, 0);
        else std::fprintf(stderr, "clusterd: --harness-udp wants IPv4:PORT, got %s\n", args.harness.c_str());
    }
    uint32_t t_harness = 0;
    size_t replay_i = 0;
    uint32_t replay_t0 = now_ms();
    const uint32_t replay_len = replay.empty() ? 0 : replay.back().t_ms + 50;

    act(shell.start());
    uint32_t t_tele = 0, t_status = 0, t_adc = 0;
    int64_t sleep_ref = boottime_minus_mono_ms();
    // Synthetic presses from --dial-stdin: release at this time.
    uint32_t stdin_release_at = 0;
    bool stdin_down = false, livi_up = false;

    for (;;) {
        pollfd fds[4];
        int nf = 0;
        int i_can = -1, i_page = -1, i_click = -1, i_stdin = -1;
        if (can >= 0) { i_can = nf; fds[nf++] = {can, POLLIN, 0}; }
        if (page >= 0) { i_page = nf; fds[nf++] = {page, POLLIN, 0}; }
        if (click >= 0) { i_click = nf; fds[nf++] = {click, POLLIN, 0}; }
        if (args.dial_stdin) { i_stdin = nf; fds[nf++] = {0, POLLIN, 0}; }
        poll(fds, nf, 5);
        uint32_t now = now_ms();

        // Were we asleep? (suspend_cmd returns after the resume, but a resume from elsewhere counts too.)
        int64_t ref = boottime_minus_mono_ms();
        if (ref - sleep_ref > 2000) {
            std::printf("clusterd: resumed after %lld s\n", (long long)((ref - sleep_ref) / 1000));
            power.resumed();
            dial.rezero();
        }
        sleep_ref = ref;

        if (i_can >= 0 && (fds[i_can].revents & POLLIN)) {
            can_frame cf;
            while (read(can, &cf, sizeof cf) == ssize_t(sizeof cf))
                if (!(cf.can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG))) bridge.on_frame(cf.can_id & CAN_SFF_MASK, cf.data, cf.can_dlc, now);
        }
        while (!replay.empty() && now - replay_t0 >= replay[replay_i].t_ms) {
            const ReplayFrame& f = replay[replay_i];
            bridge.on_frame(f.id, f.data, f.len, now);
            if (++replay_i == replay.size()) { replay_i = 0; replay_t0 += replay_len; }
        }
        if (i_page >= 0 && (fds[i_page].revents & POLLIN)) http_serve_one(page, args.web, shell, bridge, now);
        if (i_click >= 0 && (fds[i_click].revents & POLLIN)) {
            input_event ev;
            while (read(click, &ev, sizeof ev) == ssize_t(sizeof ev))
                if (ev.type == EV_KEY && ev.value != 2) act(ev.value ? shell.press(now) : shell.release(now));
        }
        if (i_stdin >= 0 && (fds[i_stdin].revents & POLLIN)) {
            char ch = 0;
            ssize_t got = read(0, &ch, 1);
            if (got <= 0) args.dial_stdin = false;   // the script ended: stop polling a closed pipe
            if (got == 1) {
                if (ch == 'q') break;
                if (ch == 'a') act(shell.turn(-1));
                if (ch == 'd') act(shell.turn(+1));
                if (!stdin_down && (ch == 'c' || ch == 'h' || ch == 'm')) {
                    act(shell.press(now));
                    stdin_down = true;
                    stdin_release_at = now + (ch == 'c' ? 100 : ch == 'h' ? 700 : 1600);
                }
            }
        }
        if (stdin_down && int32_t(now - stdin_release_at) >= 0) { act(shell.release(now)); stdin_down = false; }
        act(shell.tick(now));

        if (!args.adc.empty() && now - t_adc >= 5) {
            t_adc = now;
            std::string v = read_file(args.adc);
            if (!v.empty()) {
                int steps = dial.sample(uint32_t(std::strtoul(v.c_str(), nullptr, 10)));
                for (; steps > 0; steps--) act(shell.turn(+1));
                for (; steps < 0; steps++) act(shell.turn(-1));
            }
        }
        save_if_committed();

        if (now - t_status >= 250) {
            t_status = now;
            act(shell.set_phone(parse_livi_phone(read_file(args.livi_status))));
        }
        if (now - t_tele >= 100) {
            t_tele = now;
            if (http_post_json(cfg.livi_url_host, cfg.livi_port, "/telemetry", telemetry_json(bridge, now))) livi_up = true;
        }

        if (harness_fd >= 0 && now - t_harness >= 50) {
            t_harness = now;
            std::string l = harness_line(bridge, now, shell.ui().model().imperial, shell.gauge_theme(), shell.centre_shows_speed());
            sendto(harness_fd, l.data(), l.size(), 0, reinterpret_cast<sockaddr*>(&harness_to), sizeof harness_to);
        }

        // What gauges/ is told.
        DisplayState d;
        const hmi::Model& m = shell.ui().model();
        d.brightness_pct = uint32_t(m.brightness);
        vhal::PropValue lights = bridge.get(vhal::Prop::DashLightsOn, now);
        d.night = lights.available && lights.value != 0.0f;
        d.units_mph = m.imperial;
        d.gauge_theme = uint32_t(shell.gauge_theme());
        d.centre_shows_speed = shell.centre_shows_speed();
        tx.set_display(d);

        vhal::PropValue req = bridge.get(vhal::Prop::SuspendRequest, now);
        vhal::PropValue secs = bridge.get(vhal::Prop::SuspendInSeconds, now);
        bool suspend_now = power.update(now, req.available, req.value != 0.0f, uint32_t(secs.value));
        // "Running" once LIVI has taken a telemetry push: the centre screen is really up.
        tx.set_heartbeat(power.pending() || suspend_now ? Heartbeat::Suspending : livi_up ? Heartbeat::Running : Heartbeat::Booting);
        Frame out[LinkTx::kCount];
        int n = tx.poll(now, out);
        for (int k = 0; k < n; k++) can_send(can, out[k]);

        if (suspend_now) {
            std::printf("clusterd: ignition off, suspending (%s)\n", cfg.suspend_cmd.c_str());
            if (std::system(cfg.suspend_cmd.c_str()) != 0) std::fprintf(stderr, "clusterd: suspend command failed\n");
        }
    }

    if (tio) tcsetattr(0, TCSANOW, &saved_tio);
    if (ui >= 0) { ioctl(ui, UI_DEV_DESTROY); close(ui); }
    return 0;
}
