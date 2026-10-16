#include "panel_mock.h"

#include <string.h>

static mock_t *M(void *ctx) { return (mock_t *)ctx; }

/* level-3 and undocumented registers that only work after FEh + EFh (datasheet 6.4.8/6.4.9) */
static bool needs_unlock(int cmd)
{
    if (cmd >= 0x84 && cmd <= 0x90) return true;
    switch (cmd) {
    case 0x62: case 0x63: case 0x64: case 0x66: case 0x67: case 0x70: case 0x74: case 0x98:
    case 0xAE: case 0xBC: case 0xBD: case 0xBE: case 0xCD: case 0xDF: case 0xE1: case 0xE8:
    case 0xEB: case 0xED: case 0xC3: case 0xC4: case 0xC9: case 0xF0: case 0xF1: case 0xF2: case 0xF3:
        return true;
    default:
        return false;
    }
}

static void log_cmd(mock_t *m, int s)
{
    if (m->n_log >= MOCK_LOG_MAX || m->cur_cmd[s] < 0) return;
    mock_cmd_t *c = &m->log[m->n_log++];
    c->screen = (uint8_t)s;
    c->cmd = (uint8_t)m->cur_cmd[s];
    c->n = (uint8_t)(m->n_params[s] > 16 ? 16 : m->n_params[s]);
    memcpy(c->p, m->params[s], c->n);
}

/* finish the command in flight when a new one starts */
static void end_cmd(mock_t *m, int s)
{
    int cmd = m->cur_cmd[s];
    if (cmd < 0) return;
    log_cmd(m, s);
    if (cmd == 0x2A || cmd == 0x2B) {
        if (m->n_params[s] != 4) m->err_bad_params++;
    }
    m->cur_cmd[s] = -1;
}

static void begin_cmd(mock_t *m, int s, int cmd)
{
    end_cmd(m, s);
    m->cur_cmd[s] = cmd;
    m->n_params[s] = 0;
    m->ramwr[s] = false;
    m->have_hi[s] = false;
    m->wrapped[s] = false;

    /* datasheet 6.2.4: wait 5 ms after Sleep Out before the next command (time only advances in delay_ms) */
    if (m->slpout_seen[s] && m->ms_since_slpout[s] < 5 && m->cur_cmd[s] != 0x11) m->err_cmd_too_soon++;
    if (needs_unlock(cmd) && !m->inter_enabled[s]) m->err_inter_before_unlock++;
    if (cmd == 0xFE) m->last_was_fe[s] = true;
    else {
        if (cmd == 0xEF) {
            if (m->last_was_fe[s]) m->inter_enabled[s] = true; else m->err_bad_params++;
        }
        m->last_was_fe[s] = false;
    }
    switch (cmd) {
    case 0x11: m->sleeping[s] = false; m->slpout_seen[s] = true; m->ms_since_slpout[s] = 0; break;
    case 0x10: m->sleeping[s] = true; break;
    case 0x21: m->inverted[s] = true; break;
    case 0x20: m->inverted[s] = false; break;
    case 0x28: m->display_on[s] = false; break;
    case 0x29:
        m->display_on[s] = true;
        if (!m->slpout_seen[s] || m->ms_since_slpout[s] < 120) m->err_dispon_early++;
        break;
    case 0x2C:
        if (m->colmod[s] != 0x05) m->err_colmod++;
        m->ramwr[s] = true;
        m->col[s] = m->sc[s];
        m->row[s] = m->sp[s];
        break;
    default: break;
    }
}

static void param(mock_t *m, int s, uint8_t b)
{
    int cmd = m->cur_cmd[s];
    if (cmd < 0) { m->err_pixel_no_ramwr++; return; }
    if (cmd == 0x2C) {
        m->pixel_bytes++;
        if (!m->have_hi[s]) { m->hi[s] = b; m->have_hi[s] = true; return; }
        m->have_hi[s] = false;
        uint16_t px = (uint16_t)((m->hi[s] << 8) | b);
        if (m->wrapped[s]) { m->err_wrap++; m->wrapped[s] = false; }   /* more pixels than the window holds */
        int x = m->col[s], y = m->row[s];
        if (x < 0 || x > 239 || y < 0 || y > 239 || x < m->sc[s] || x > m->ec[s] || y < m->sp[s] || y > m->ep[s]) {
            m->err_window++;
        } else {
            m->fb[s][y * 240 + x] = px;
            m->written[s][y * 240 + x] = true;
        }
        if (++m->col[s] > m->ec[s]) {
            m->col[s] = m->sc[s];
            if (++m->row[s] > m->ep[s]) { m->row[s] = m->sp[s]; m->wrapped[s] = true; }
        }
        return;
    }
    if (m->n_params[s] < 16) m->params[s][m->n_params[s]] = b;
    m->n_params[s]++;
    switch (cmd) {
    case 0x2A: if (m->n_params[s] == 4) { m->sc[s] = (m->params[s][0] << 8) | m->params[s][1]; m->ec[s] = (m->params[s][2] << 8) | m->params[s][3]; } break;
    case 0x2B: if (m->n_params[s] == 4) { m->sp[s] = (m->params[s][0] << 8) | m->params[s][1]; m->ep[s] = (m->params[s][2] << 8) | m->params[s][3]; } break;
    case 0x3A: m->colmod[s] = b; break;
    case 0x36: m->madctl[s] = b; break;
    default: break;
    }
}

/* ---- HAL ---- */

static void h_select(void *ctx, uint8_t s, bool on)
{
    mock_t *m = M(ctx);
    if (on) {
        if (m->selected >= 0) m->err_two_cs++;
        m->selected = s;
        m->cs[s] = true;
        m->spans++;
    } else {
        end_cmd(m, s);                                  /* a command ends when CS rises */
        m->cs[s] = false;
        if (m->selected == s) m->selected = -1;
    }
}

static void h_dc(void *ctx, uint8_t s, bool data) { M(ctx)->dc_data[s] = data; }

static void h_reset(void *ctx, bool asserted)
{
    mock_t *m = M(ctx);
    if (asserted && !m->reset_asserted) {
        m->reset_count++;
        for (int s = 0; s < MOCK_SCREENS; s++) {
            m->inter_enabled[s] = false; m->display_on[s] = false; m->sleeping[s] = true;
            m->inverted[s] = false; m->slpout_seen[s] = false; m->cur_cmd[s] = -1; m->colmod[s] = 0x06; m->last_was_fe[s] = false;
            m->sc[s] = 0; m->ec[s] = 239; m->sp[s] = 0; m->ep[s] = 239;
        }
    }
    m->reset_asserted = asserted;
}

static void h_write(void *ctx, const uint8_t *buf, uint32_t len)
{
    mock_t *m = M(ctx);
    m->bytes_written += len;
    if (m->reset_asserted) { m->err_in_reset++; return; }
    int s = m->selected;
    if (s < 0) { m->err_no_cs++; return; }
    for (uint32_t i = 0; i < len; i++) {
        if (!m->dc_data[s]) begin_cmd(m, s, buf[i]);
        else param(m, s, buf[i]);
    }
}

static void h_delay(void *ctx, uint32_t ms)
{
    mock_t *m = M(ctx);
    m->total_delay_ms += ms;
    for (int s = 0; s < MOCK_SCREENS; s++) m->ms_since_slpout[s] += ms;
}

static void h_backlight(void *ctx, bool on) { M(ctx)->backlight = on; }

static panel_hal_t g_hal;

void mock_init(mock_t *m)
{
    memset(m, 0, sizeof *m);
    m->selected = -1;
    for (int s = 0; s < MOCK_SCREENS; s++) {
        m->cur_cmd[s] = -1;
        m->sleeping[s] = true;
        m->ec[s] = 239; m->ep[s] = 239;
        m->colmod[s] = 0x06;
    }
}

const panel_hal_t *mock_hal(mock_t *m)
{
    g_hal.ctx = m;
    g_hal.select = h_select;
    g_hal.dc = h_dc;
    g_hal.reset = h_reset;
    g_hal.write = h_write;
    g_hal.delay_ms = h_delay;
    g_hal.backlight = h_backlight;
    return &g_hal;
}

int mock_errors(const mock_t *m)
{
    return m->err_no_cs + m->err_two_cs + m->err_in_reset + m->err_pixel_no_ramwr + m->err_window +
           m->err_wrap + m->err_inter_before_unlock + m->err_colmod + m->err_dispon_early +
           m->err_bad_params + m->err_odd_pixel_bytes + m->err_cmd_too_soon;
}

int mock_count(const mock_t *m, int screen, int cmd)
{
    int n = 0;
    for (int i = 0; i < m->n_log; i++)
        if ((screen < 0 || m->log[i].screen == screen) && m->log[i].cmd == cmd) n++;
    return n;
}
