# Main Test Directory - CPU Memory Initialization

## Quick Start

This directory contains files for initializing the Assassyn CPU's main memory and instruction cache.

### Files

- **`data.bin`** - Data segment binary file (example provided)
- **`text.bin`** - Instruction segment binary file (example provided)
- **`convert_bin_to_exe.py`** - Conversion script
- **`初始化报告.md`** - Detailed report in Chinese
- **`INITIALIZATION_REPORT.md`** - Detailed report in English

### Usage

1. **Convert binary files to Assassyn format:**
   ```bash
   python3 convert_bin_to_exe.py
   ```

2. **Run CPU simulation:**
   ```bash
   cd ..
   python src/main.py
   ```

### What Happens

The conversion script:
- Reads `data.bin` and `text.bin`
- Converts them to ASCII hex format
- Saves to `.workspace/workload_mem.exe` and `.workspace/workload_ins.exe`
- Creates `.workspace/workload.init` for offset initialization

The CPU (`src/main.py`) automatically loads these files during initialization.

### Example Files Provided

The repository includes example files:
- **data.bin**: 8 words (32 bytes) of sample data
- **text.bin**: 8 RISC-V instructions (32 bytes)

### Creating Custom Files

#### Option 1: Python Script
```python
import struct

# Create your own data.bin
with open('data.bin', 'wb') as f:
    for value in [0x00, 0x01, 0x02, 0x03]:
        f.write(struct.pack('<I', value))

# Create your own text.bin (RISC-V instructions)
with open('text.bin', 'wb') as f:
    for instr in [0x00000013, 0x00100093]:  # NOP, addi x1,x0,1
        f.write(struct.pack('<I', instr))
```

#### Option 2: From RISC-V Toolchain
```bash
riscv32-unknown-elf-objcopy -O binary --only-section=.text program.elf text.bin
riscv32-unknown-elf-objcopy -O binary --only-section=.data program.elf data.bin
```

### File Format

- **Binary files (.bin)**: Raw binary, little-endian, 32-bit words
- **Initialization files (.exe)**: ASCII hex, one 32-bit word per line, 8 hex digits

### For More Information

See the detailed reports:
- Chinese: [初始化报告.md](初始化报告.md)
- English: [INITIALIZATION_REPORT.md](INITIALIZATION_REPORT.md)

---

**Quick Commands:**
```bash
# Convert files
python3 convert_bin_to_exe.py

# Verify output
cat ../.workspace/workload_mem.exe
cat ../.workspace/workload_ins.exe

# Run CPU
cd .. && python src/main.py
```
