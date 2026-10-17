#ifndef BOOT_REQUEST_H
#define BOOT_REQUEST_H
/* A 16-byte note left in the retained RAM (linker script: the first 16 bytes of .noinit) for the bootloader to find after a reset.
 * REAL, host-tested. The application writes ENTER before it resets to be reflashed; the bootloader writes RUN before it resets to
 * make the next start run the application whatever the fault record says. The note is valid only if its magic, the value and the
 * value's complement agree; the reader clears it, so a request is honoured once. After a power-on reset the area is zeroed. */
#include <stdbool.h>
#include <stdint.h>

#define BOOTREQ_NONE   0u
#define BOOTREQ_ENTER  0x45544E45u      /* stay in the bootloader and wait for an update */
#define BOOTREQ_RUN    0x4E555252u      /* run the application now, even if it has been failing */

typedef struct {
    uint32_t magic;
    uint32_t value;
    uint32_t value_inv;
    uint32_t pad;
} boot_request_t;

#define BOOTREQ_MAGIC 0x51455242u

void     bootreq_write(boot_request_t *r, uint32_t value);
uint32_t bootreq_take(boot_request_t *r);            /* the value if the note is valid (and clears it), else BOOTREQ_NONE */

/* The note in the retained RAM of this image. */
extern boot_request_t g_bootreq;

#endif
