riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -nostdlib -Wl,--no-check-sections -T harvard.ld start.S code.c -o cpu.elf
riscv64-unknown-elf-objcopy -j .text -O binary cpu.elf icache.bin
riscv64-unknown-elf-objcopy -j .data -j .bss -O binary cpu.elf memory.bin
riscv64-linux-gnu-objdump -D cpu.elf > obj.exe
hexdump -v -e '1/4 "%08x" "\n"' icache.bin > icache.hex
hexdump -v -e '1/4 "%08x" "\n"' memory.bin > memory.hex