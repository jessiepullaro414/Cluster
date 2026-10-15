#!/bin/sh
# Print the facts that matter about the firmware image: section placement, the
# first vectors, the flash configuration field and the reset code.
# Usage (from gauges-fw/, in WSL): sh tools/inspect_elf.sh [elf]
ELF=${1:-build/gauges-fw.elf}
B=${ARMBIN:-/opt/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi/bin/arm-none-eabi-}
${B}readelf -S -W "$ELF" | grep -E "isr_vector|flashconfig| \.text| \.data| \.bss"
echo "--- first 16 vector words"
${B}objdump -s -j .isr_vector "$ELF" | sed -n 4,7p
echo "--- flash configuration field (0x400)"
${B}objdump -s -j .flashconfig "$ELF" | tail -n +4
echo "--- key symbols"
${B}nm "$ELF" | grep -E " (Reset_Handler|Reset_C|SysTick_Handler|Default_Handler|_estack|__ram_start|g_vectors|g_flash_config)$"
echo "--- Reset_Handler"
${B}objdump -d "$ELF" --disassemble=Reset_Handler | tail -n +7
