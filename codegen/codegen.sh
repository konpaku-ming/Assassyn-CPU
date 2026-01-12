riscv64-unknown-elf-gcc -march=rv32i -mabi=ilp32 -nostdlib -Wl,--no-check-sections -T Neumann.ld start.S code.c -o cpu.elf
riscv64-unknown-elf-objcopy -O binary cpu.elf memory.bin
riscv64-linux-gnu-objdump -D cpu.elf > obj.exe
hexdump -v -e '1/4 "%08x" "\n"' memory.bin > memory.hex