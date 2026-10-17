/* S32K144 linker script. Addresses are from NXP's S32K1xx_Memory_Map.xlsx
 * (S32K144 column) and RM chapters 25 and 31:
 *   program flash 0x0000_0000 - 0x0007_FFFF (512 KB)
 *   SRAM_L        0x1FFF_8000 - 0x1FFF_FFFF, SRAM_U 0x2000_0000 - 0x2000_6FFF
 *                 (contiguous, 60 KB)
 * The vector table sits at 0x0 (reset fetches SP from 0x0 and PC from 0x4) and
 * the 16-byte flash configuration field at 0x400 (RM 25.3.1). FlexNVM
 * (0x1000_0000) and FlexRAM (0x1400_0000) are not used yet. */
ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 512K
    RAM   (rwx) : ORIGIN = 0x1FFF8000, LENGTH = 60K
}

STACK_MIN = 2K;
NOINIT_SIZE = 64;      /* top of RAM, kept across a watchdog or software reset: [0,16) the boot request (src/boot_request.c),
                          [16,64) the fault manager's record (src/fault.c). Identical in the application and the bootloader. */

SECTIONS
{
    .isr_vector 0x0 : { KEEP(*(.isr_vector)) } > FLASH
    ASSERT(SIZEOF(.isr_vector) <= 0x400, "vector table overruns the flash configuration field")

    .flashconfig 0x400 : { KEEP(*(.flashconfig)) } > FLASH
    ASSERT(SIZEOF(.flashconfig) == 16, "flash configuration field must be exactly 16 bytes")

    .text : ALIGN(4)
    {
        *(.text*)
        *(.rodata*)
        KEEP(*(.init))
        KEEP(*(.fini))
        . = ALIGN(4);
    } > FLASH

    .ARM.exidx : { *(.ARM.exidx*) } > FLASH

    .data : ALIGN(4)
    {
        __data_start = .;
        *(.data*)
        *(.ramfunc*)         /* code that must run from SRAM (nvflash_s32k.c: Program Partition) */
        . = ALIGN(4);
        __data_end = .;
    } > RAM AT > FLASH
    __data_load = LOADADDR(.data);

    .bss (NOLOAD) : ALIGN(4)
    {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > RAM

    /* The stack grows down from _estack; the retained record sits above it and is NOT zeroed by the startup fill
     * (only after a power-on reset, where SRAM holds nothing valid: startup.c). */
    __ram_start = ORIGIN(RAM);
    _estack = ORIGIN(RAM) + LENGTH(RAM) - NOINIT_SIZE;
    .noinit _estack (NOLOAD) : ALIGN(4)
    {
        __noinit_start = .;
        KEEP(*(.noinit.bootreq))
        __bootreq_end = .;
        . = __noinit_start + 16;
        __faultrec_start = .;
        KEEP(*(.noinit.fault))
        __faultrec_end = .;
        . = __noinit_start + NOINIT_SIZE;       /* the whole area, so the startup code writes all of it after a power-on reset */
        __noinit_end = .;
    } > RAM
    ASSERT(__bootreq_end - __noinit_start <= 16, "boot request larger than 16 bytes")
    ASSERT(__faultrec_end - __faultrec_start <= 48, "fault record larger than 48 bytes")
    ASSERT(__bss_end + STACK_MIN <= _estack, "less than STACK_MIN left for the stack")

    /DISCARD/ : { *(.comment) *(.note*) }
}
