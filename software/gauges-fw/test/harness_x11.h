#ifndef HARNESS_X11_H
#define HARNESS_X11_H
/* Minimal window for the test harness: show an ARGB pixel buffer, deliver key and close events.
 * Plain Xlib; on Windows 11 the WSLg X server draws it on the desktop. Only harness.c uses it. */
#include <stdbool.h>
#include <stdint.h>

typedef struct x11win x11win_t;

typedef enum { HEV_NONE = 0, HEV_QUIT, HEV_KEY, HEV_RESIZE } hev_type_t;

typedef struct {
    hev_type_t type;
    int        key;         /* HEV_KEY: ASCII for printable keys, or one of the HK_ codes */
} hev_t;

enum { HK_UP = 0x100, HK_DOWN, HK_LEFT, HK_RIGHT, HK_ESC, HK_ENTER, HK_BACKSPACE };

/* NULL if there is no display. */
x11win_t *x11_open(int w, int h, const char *title);
void      x11_close(x11win_t *);
/* Copy a w x h 0x00RRGGBB buffer to the window (the window is resized if the size changed). */
void      x11_present(x11win_t *, const uint32_t *argb, int w, int h);
/* Next pending event; HEV_NONE when the queue is empty. Never blocks. */
bool      x11_poll(x11win_t *, hev_t *out);
/* Read the window contents back from the X server (to prove what is on screen). Returns false on failure. */
bool      x11_readback(x11win_t *, uint32_t *argb, int w, int h);
#endif
