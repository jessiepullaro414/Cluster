#!/usr/bin/env bash
# Build the whole PC bench in a fresh Ubuntu-24.04 WSL distro, as root: everything the aa-bench README describes,
# in one go (about 20-30 minutes, about 2 GB of downloads).
#
#   wsl --install -d Ubuntu-24.04 --no-launch
#   wsl -d Ubuntu-24.04 -u root -e bash /mnt/c/Users/root/Project/cluster-pcb/software/linux/aa-bench/setup_bench_distro.sh
#
# What it does:
#   * system packages: LIVI's runtime libraries, build tools, Roboto fonts (our gauge faces), Tk (the car panel)
#   * libva 2.22 and wayland 1.23 from source into /usr (Ubuntu 24.04 has 2.20 / 1.22; LIVI's bundled FFmpeg and
#     waylandsink need the newer ones)
#   * LIVI's current nightly AppImage, extracted to /root/livi-bench/app
#   * LIVI's source at the nightly's own commit, with our two patches (livi-tcp-without-bt.patch: bench only;
#     ../livi/livi-round-ui.patch: customHideNav), the rebuilt livi-core, livi-helperd and UI bundle dropped into the
#     extracted AppImage (Node 24 from nodejs.org, checksum-checked)
#   * clusterd built for this distro, LIVI's config from ../livi/livi_config.py, a can_replay drive log
# It stops at the first failure (set -e); every step can be rerun.
set -euo pipefail
REPO=/mnt/c/Users/root/Project/cluster-pcb
B=/root/livi-bench
export DEBIAN_FRONTEND=noninteractive
mkdir -p "$B"
log() { printf '\n==== %s\n' "$*"; }

log "system packages"
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    build-essential pkg-config git curl ca-certificates xz-utils python3 python3-pip python3-tk \
    libdbus-1-dev libudev-dev libssl-dev \
    libgtk-3-0t64 libnss3 libva2 libva-drm2 libva-x11-2 libssh-4 libasound2t64 libgbm1 libxss1 libxtst6 \
    pulseaudio-utils bluez avahi-utils iproute2 \
    libwayland-server0 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-libav gstreamer1.0-plugins-bad libegl1 libgles2 \
    meson ninja-build libdrm-dev libx11-dev libxext-dev libxfixes-dev libwayland-dev libexpat1-dev libxml2-dev libffi-dev \
    fonts-roboto can-utils > "$B/apt.log"
pip3 install --break-system-packages -q cantools

log "libva 2.22.0 and wayland 1.23.1 into /usr"
cd "$B"
rm -rf libva wayland
git -c advice.detachedHead=false clone -q --depth 1 --branch 2.22.0 https://github.com/intel/libva libva
(cd libva && meson setup b --prefix=/usr --libdir=lib/x86_64-linux-gnu -Dwith_glx=no > /dev/null && ninja -C b install > /dev/null)
git -c advice.detachedHead=false clone -q --depth 1 --branch 1.23.1 https://gitlab.freedesktop.org/wayland/wayland.git wayland
(cd wayland && meson setup b --prefix=/usr --libdir=lib/x86_64-linux-gnu -Ddocumentation=false -Dtests=false > /dev/null && ninja -C b install > /dev/null)
ldconfig
nm -D /usr/lib/x86_64-linux-gnu/libva.so.2 | grep -q vaMapBuffer2
nm -D /usr/lib/x86_64-linux-gnu/libwayland-client.so.0 | grep -q wl_display_create_queue_with_name

log "LIVI nightly: which commit, and its AppImage"
REL=$(curl -s https://api.github.com/repos/f-io/LIVI/releases/tags/nightly)
COMMIT=$(printf '%s' "$REL" | grep -o '"name": "Nightly #[0-9]* · dev ([0-9a-f]*)"' | grep -o '([0-9a-f]*)' | tr -d '()')
URL=$(printf '%s' "$REL" | grep -o '"browser_download_url": "[^"]*linux-x86_64.AppImage"' | cut -d'"' -f4)
[ -n "$COMMIT" ] && [ -n "$URL" ] || { echo "could not read the nightly release"; exit 1; }
echo "nightly commit $COMMIT, $URL"
mkdir -p dl app
curl -sSL -o dl/LIVI.AppImage "$URL"
chmod +x dl/LIVI.AppImage
(cd app && rm -rf squashfs-root && ../dl/LIVI.AppImage --appimage-extract > /dev/null)
R=$B/app/squashfs-root/resources

log "LIVI source at $COMMIT with our patches"
rm -rf src
git clone -q --branch dev --single-branch https://github.com/f-io/LIVI src
git -C src -c advice.detachedHead=false checkout -q "$COMMIT"
for p in "$REPO/software/linux/aa-bench/livi-tcp-without-bt.patch" "$REPO/software/linux/livi/livi-round-ui.patch"; do
    tr -d '\r' < "$p" > /tmp/patch.diff
    git -C src apply --recount /tmp/patch.diff || { echo "patch does not apply at $COMMIT: $p"; exit 1; }
done

log "Rust: regenerate LIVI's TypeScript contract, build livi-core and livi-helperd"
[ -x /root/.cargo/bin/rustup ] || curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none > /dev/null
. /root/.cargo/env
# LIVI pins a beta toolchain in rust-toolchain.toml; install it as its own step (rustup's auto-install inside the first
# cargo call died once on a fresh distro, exit code 4, and worked when rerun)
(cd src && rustup toolchain install)
(cd src && LIVI_WRITE_CONTRACT=1 cargo test -q --manifest-path native/Cargo.toml -p livi-core-proto typescript_contract_is_current > /dev/null)
(cd src && cargo build -q --release --manifest-path native/Cargo.toml -p livi-helperd -p livi-core)

log "Node 24 and LIVI's UI bundle"
NODE=$(curl -s https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt | grep -o 'node-v24[0-9.]*-linux-x64.tar.xz' | head -1)
curl -sSLO "https://nodejs.org/dist/latest-v24.x/$NODE"
curl -s https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt | grep " $NODE\$" | sha256sum -c -
rm -rf node && mkdir node && tar -xJf "$NODE" -C node --strip-components=1 && rm -f "$NODE"
export PATH=$B/node/bin:$PATH ELECTRON_SKIP_BINARY_DOWNLOAD=1 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
(cd src && corepack enable pnpm && pnpm install --frozen-lockfile > "$B/pnpm.log" 2>&1 && pnpm run build:app > "$B/vite.log" 2>&1)
grep -q customHideNav src/out/renderer/index.js

log "drop our builds into the extracted AppImage"
cp "$R/app.asar" "$R/app.asar.orig"
rm -rf asar-x
npx -y @electron/asar extract "$R/app.asar.orig" asar-x
rm -rf asar-x/out && cp -r src/out asar-x/out
npx -y @electron/asar pack asar-x "$R/app.asar"
cp "$R/core/livi-core" "$R/core/livi-core.orig"; cp src/native/target/release/livi-core "$R/core/livi-core"
cp "$R/driver/livi-helperd" "$R/driver/livi-helperd.orig"; cp src/native/target/release/livi-helperd "$R/driver/livi-helperd"

log "clusterd, LIVI's config, a drive log"
make -s -C "$REPO/software/linux/clusterd" clean build/clusterd
cp "$REPO/software/linux/clusterd/build/clusterd" "$B/clusterd-bin"
make -s -C "$REPO/software/linux/clusterd" clean        # the shared build folder: leave no binary for the other distro
python3 "$REPO/software/tools/can_replay.py" --role gauges --dry-run --seconds 60 > "$B/drive.txt" 2> /dev/null
mkdir -p /root/.config/LIVI
python3 "$REPO/software/linux/livi/livi_config.py" --apply /root/.config/LIVI/config.json --shape 0 --car-name "1966 Mustang"
python3 - <<'EOF'
import json
p = "/root/.config/LIVI/config.json"
d = json.load(open(p))
d["mainScreenBounds"] = {"x": 200, "y": 120, "width": 720, "height": 720}
json.dump(d, open(p, "w"), indent=2)
EOF

log "done: double-click software\\linux\\sim\\start_car_sim.cmd"
