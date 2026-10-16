#!/bin/sh
# Fetch the X11 development headers WITHOUT root: download the .deb files and unpack them into a
# private directory (~/x11sdk). Headers only (text files); nothing is installed or executed.
# Needed only for the harness window (make harness); the automated modes need no X11.
set -e
D=$HOME/x11sdk
rm -rf "$D"; mkdir -p "$D/debs" "$D/root"
cd "$D/debs"
apt-get download libx11-dev x11proto-dev
for f in *.deb; do dpkg -x "$f" "$D/root"; done
ls "$D/root/usr/include/X11/Xlib.h"
