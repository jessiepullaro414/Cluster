/* Flash configuration field, 16 bytes at 0x400 (RM 25.3.1; the linker script
 * places the section and asserts its size). These bytes are read at every
 * reset. Values:
 *   backdoor key  8 x 0xFF
 *   FPROT0-3      0xFF   no program-flash region protected
 *   FSEC          0xFE   KEYEN 11, MEEN 11, FSLACC 11, SEC 10 = UNSECURED.
 *                        Production must change this (SEC = 00 secured), and
 *                        that makes the part undebuggable without a mass erase.
 *   FOPT          0xFB   bit 3 RESET_PIN_CFG = 1 (RESET pin enabled),
 *                        bit 2 NMI_PIN_CFG = 0 (NMI pin disabled; the RM
 *                        recommends it when unused), bit 0 LPBOOT = 1 (core
 *                        clock divide-by-1 out of reset), other bits reserved 1
 *   FEPROT, FDPROT 0xFF  no EEPROM / data-flash protection */
#include <stdint.h>

__attribute__((section(".flashconfig"), used))
const uint8_t g_flash_config[16] = {
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,     /* 0x400 backdoor key */
#ifdef BOOT_BUILD
    /* 0x408 is FPROT3 = regions 0-7 of 16 KB each (RM 36.4.4.1.8: FPROT3 holds PROT[7:0]); a 0 bit write-protects a region. Regions 0
     * and 1 are the bootloader's 32 KB: no flash command, so no bug in the update path, can erase them (only an erase-all from the debugger). */
    0xFC, 0xFF, 0xFF, 0xFF,                             /* 0x408 FPROT3, FPROT2, FPROT1, FPROT0 */
#else
    0xFF, 0xFF, 0xFF, 0xFF,                             /* 0x408 FPROT3..FPROT0: nothing protected */
#endif
    0xFE,                                               /* 0x40C FSEC        */
    0xFB,                                               /* 0x40D FOPT        */
    0xFF,                                               /* 0x40E FEPROT      */
    0xFF,                                               /* 0x40F FDPROT      */
};
