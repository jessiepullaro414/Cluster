"""Capture one desktop window's own pixels on Windows (Win32 PrintWindow with PW_RENDERFULLCONTENT), so the window may be
covered by others while it records. Used for LIVI's window (a WSLg window) in the Linux-option demo.

    from wincap import find_window, capture
    h = find_window("LIVI")
    img = capture(h)          # numpy uint8 array, H x W x 3, BGR (OpenCV order)
"""
import ctypes
from ctypes import wintypes

import numpy as np

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.SetProcessDPIAware()

PW_RENDERFULLCONTENT = 2
DIB_RGB_COLORS = 0
BI_RGB = 0
SRCCOPY = 0x00CC0020

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT]


def find_window(title_part):
    """The first visible top-level window whose title contains title_part, or None."""
    found = []

    def cb(h, _):
        if user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, 256)
            if title_part in buf.value:
                found.append(h)
                return False
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else None


def capture(hwnd):
    """The window's pixels (BGR), including its frame, as the window draws them."""
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        if not user32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT):
            raise OSError("PrintWindow failed")
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, BI_RGB, 0, 0, 0, 0, 0)
        buf = np.empty((h, w, 4), np.uint8)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf.ctypes.data, ctypes.byref(bi), DIB_RGB_COLORS)
        return buf[:, :, :3].copy()
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, wdc)


if __name__ == "__main__":
    import sys
    import time

    import cv2
    h = find_window(sys.argv[1] if len(sys.argv) > 1 else "LIVI")
    if not h:
        raise SystemExit("window not found")
    t0 = time.time()
    for i in range(20):
        img = capture(h)
    dt = (time.time() - t0) / 20
    cv2.imwrite(sys.argv[2] if len(sys.argv) > 2 else "wincap_test.png", img)
    print(f"{img.shape[1]}x{img.shape[0]}, {dt * 1000:.1f} ms per capture")
