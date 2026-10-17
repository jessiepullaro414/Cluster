/* Feed the frames that tools/can_flash.py --emit wrote (one "ID#HEX" per line) into the bootloader core over the flash model, print
 * every answer, and write the application region of the flash to a file. tools/test_can_flash.py compares the file with the image:
 * the proof that the Python tool and the C bootloader agree on framing, sequence numbers and CRC. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bootcore.h"
#include "pflash_mock.h"

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: boot_replay frames.txt dump.bin\n"); return 2; }
    FILE *f = fopen(argv[1], "r");
    if (!f) { perror("frames"); return 2; }
    pf_reset();
    bootcore_t bc;
    bootcore_init(&bc, &pflash_mock, BOARD_ID_GAUGES);
    char line[128];
    unsigned long t = 0;
    int bad = 0;
    while (fgets(line, sizeof line, f)) {
        unsigned id; char hex[40];
        if (sscanf(line, "%x#%39s", &id, hex) != 2) continue;
        can_frame_t in = { (uint16_t)id, (uint8_t)(strlen(hex) / 2), { 0 } }, out;
        for (unsigned i = 0; i < in.dlc && i < 8; i++) { unsigned v; sscanf(hex + 2 * i, "%2x", &v); in.data[i] = (uint8_t)v; }
        t += 3;
        if (bootcore_on_frame(&bc, &in, &out, (uint32_t)t)) {
            printf("R %03X %02X %02X %02X\n", out.id, out.data[0], out.data[1], out.data[2]);
            if (out.data[1] != 0) bad++;
        }
    }
    fclose(f);
    printf("STATE %d BOOT_REQUESTED %d VIOLATIONS %u BOOT_TOUCHED %u BAD_RESPONSES %d\n", (int)bc.state, (int)bc.boot_requested, pf_violations, pf_boot_touched, bad);
    FILE *o = fopen(argv[2], "wb");
    if (!o) { perror("dump"); return 2; }
    fwrite(pf_mem + APP_BASE, 1, APP_SIZE, o);
    fclose(o);
    return 0;
}
