#include "harness_x11.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>

struct x11win {
    Display *dpy;
    int      screen;
    Window   win;
    GC       gc;
    Atom     wm_delete;
    XImage  *img;
    uint32_t *pixels;
    int      w, h;
};

static XImage *make_image(x11win_t *x, int w, int h)
{
    free(x->pixels);
    x->pixels = (uint32_t *)calloc((size_t)w * (size_t)h, 4);
    if (!x->pixels) return 0;
    Visual *vis = DefaultVisual(x->dpy, x->screen);
    XImage *im = XCreateImage(x->dpy, vis, (unsigned)DefaultDepth(x->dpy, x->screen), ZPixmap, 0,
                              (char *)x->pixels, (unsigned)w, (unsigned)h, 32, 0);
    return im;
}

x11win_t *x11_open(int w, int h, const char *title)
{
    Display *d = XOpenDisplay(0);
    if (!d) return 0;
    x11win_t *x = (x11win_t *)calloc(1, sizeof *x);
    x->dpy = d;
    x->screen = DefaultScreen(d);
    x->w = w;  x->h = h;
    x->win = XCreateSimpleWindow(d, RootWindow(d, x->screen), 80, 80, (unsigned)w, (unsigned)h, 0,
                                 BlackPixel(d, x->screen), BlackPixel(d, x->screen));
    XStoreName(d, x->win, title);
    XSelectInput(d, x->win, ExposureMask | KeyPressMask | KeyReleaseMask | ButtonPressMask | ButtonReleaseMask | StructureNotifyMask);
    x->wm_delete = XInternAtom(d, "WM_DELETE_WINDOW", False);
    XSetWMProtocols(d, x->win, &x->wm_delete, 1);
    x->gc = XCreateGC(d, x->win, 0, 0);
    x->img = make_image(x, w, h);
    XMapWindow(d, x->win);
    XFlush(d);
    return x;
}

void x11_close(x11win_t *x)
{
    if (!x) return;
    if (x->img) { x->img->data = 0; XDestroyImage(x->img); }     /* the pixels are ours */
    free(x->pixels);
    XFreeGC(x->dpy, x->gc);
    XDestroyWindow(x->dpy, x->win);
    XCloseDisplay(x->dpy);
    free(x);
}

void x11_present(x11win_t *x, const uint32_t *argb, int w, int h)
{
    if (w != x->w || h != x->h) {
        if (x->img) { x->img->data = 0; XDestroyImage(x->img); }
        x->img = make_image(x, w, h);
        x->w = w;  x->h = h;
        XResizeWindow(x->dpy, x->win, (unsigned)w, (unsigned)h);
    }
    memcpy(x->pixels, argb, (size_t)w * (size_t)h * 4);
    XPutImage(x->dpy, x->win, x->gc, x->img, 0, 0, 0, 0, (unsigned)w, (unsigned)h);
    XFlush(x->dpy);
}

bool x11_poll(x11win_t *x, hev_t *out)
{
    while (XPending(x->dpy)) {
        XEvent e;
        XNextEvent(x->dpy, &e);
        out->type = HEV_NONE;
        out->key = 0;
        switch (e.type) {
        case Expose:
            if (x->img) XPutImage(x->dpy, x->win, x->gc, x->img, 0, 0, 0, 0, (unsigned)x->w, (unsigned)x->h);
            break;
        case ClientMessage:
            if ((Atom)e.xclient.data.l[0] == x->wm_delete) { out->type = HEV_QUIT; return true; }
            break;
        case KeyPress: {
            char buf[8];
            KeySym ks = 0;
            int n = XLookupString(&e.xkey, buf, sizeof buf, &ks, 0);
            out->type = HEV_KEY;
            switch (ks) {
            case XK_Up: out->key = HK_UP; break;
            case XK_Down: out->key = HK_DOWN; break;
            case XK_Left: out->key = HK_LEFT; break;
            case XK_Right: out->key = HK_RIGHT; break;
            case XK_Escape: out->key = HK_ESC; break;
            case XK_Return: out->key = HK_ENTER; break;
            case XK_BackSpace: out->key = HK_BACKSPACE; break;
            default:
                if (n == 1 && (unsigned char)buf[0] >= 32 && (unsigned char)buf[0] < 127) out->key = (unsigned char)buf[0];
                else out->type = HEV_NONE;
                break;
            }
            if (out->type == HEV_KEY) return true;
            break;
        }
        case KeyRelease: {
            char buf[8];
            KeySym ks = 0;
            int n = XLookupString(&e.xkey, buf, sizeof buf, &ks, 0);
            int code = 0;
            switch (ks) {
            case XK_Up: code = HK_UP; break;
            case XK_Down: code = HK_DOWN; break;
            case XK_Left: code = HK_LEFT; break;
            case XK_Right: code = HK_RIGHT; break;
            case XK_Escape: code = HK_ESC; break;
            case XK_Return: code = HK_ENTER; break;
            case XK_BackSpace: code = HK_BACKSPACE; break;
            default: if (n == 1 && (unsigned char)buf[0] >= 32 && (unsigned char)buf[0] < 127) code = (unsigned char)buf[0]; break;
            }
            if (code) { out->type = HEV_KEY_UP; out->key = code; return true; }
            break;
        }
        case ButtonPress:
            if (e.xbutton.button == 4) { out->type = HEV_WHEEL; out->key = +1; return true; }
            if (e.xbutton.button == 5) { out->type = HEV_WHEEL; out->key = -1; return true; }
            out->type = HEV_MOUSE_DOWN; out->key = (int)e.xbutton.button;
            return true;
        case ButtonRelease:
            if (e.xbutton.button == 4 || e.xbutton.button == 5) break;
            out->type = HEV_MOUSE_UP; out->key = (int)e.xbutton.button;
            return true;
        default:
            break;
        }
    }
    return false;
}

bool x11_readback(x11win_t *x, uint32_t *argb, int w, int h)
{
    XSync(x->dpy, False);
    XImage *im = XGetImage(x->dpy, x->win, 0, 0, (unsigned)w, (unsigned)h, AllPlanes, ZPixmap);
    if (!im) return false;
    for (int y = 0; y < h; y++)
        for (int xx = 0; xx < w; xx++)
            argb[y * w + xx] = (uint32_t)XGetPixel(im, xx, y) & 0x00FFFFFFu;
    XDestroyImage(im);
    return true;
}
