# Quick Reference - CPU Memory Initialization

## TL;DR

```bash
cd main_test
python3 convert_bin_to_exe.py
cd ..
python src/main.py
```

## Files in This Directory

| File | Purpose |
|------|---------|
| `data.bin` | Example data segment (8 words, 32 bytes) |
| `text.bin` | Example instruction segment (8 instructions, 32 bytes) |
| `convert_bin_to_exe.py` | Conversion script (binary → Assassyn format) |
| `verify_conversion.py` | Verification script (check conversion correctness) |
| `README.md` | Quick start guide |
| `初始化报告.md` | Detailed report in Chinese |
| `INITIALIZATION_REPORT.md` | Detailed report in English |
| `QUICK_REFERENCE.md` | This file |

## Command Reference

### Convert Binary Files
```bash
python3 convert_bin_to_exe.py
```

### Verify Conversion
```bash
python3 verify_conversion.py
```

### Create Custom data.bin
```python
import struct
with open('data.bin', 'wb') as f:
    for value in [0x1234, 0x5678, 0xABCD]:
        f.write(struct.pack('<I', value))
```

### Create Custom text.bin (RISC-V instructions)
```python
import struct
instructions = [
    0x00000013,  # NOP
    0x00100093,  # addi x1, x0, 1
    0x00200113,  # addi x2, x0, 2
]
with open('text.bin', 'wb') as f:
    for instr in instructions:
        f.write(struct.pack('<I', instr))
```

### View Generated Files
```bash
cat ../.workspace/workload_mem.exe
cat ../.workspace/workload_ins.exe
cat ../.workspace/workload.init
```

## File Format Cheat Sheet

### Binary Format (.bin)
- **Encoding**: Raw binary
- **Byte order**: Little-endian (LSB first)
- **Word size**: 32-bit (4 bytes)
- **Example**: `0x12345678` → bytes `78 56 34 12`

### Initialization Format (.exe)
- **Encoding**: ASCII text
- **Format**: 8-digit hex per line (lowercase)
- **No prefix**: Don't use `0x`
- **Example**:
  ```
  12345678
  deadbeef
  cafebabe
  ```

## Memory Map

| Component | Init File | Source | Address Range |
|-----------|-----------|--------|---------------|
| Data Memory (main_memory) | `.workspace/workload_mem.exe` | `data.bin` | 0x00000000 - 0x0000FFFF |
| Instruction Cache (icache) | `.workspace/workload_ins.exe` | `text.bin` | 0x00000000 - 0x0000FFFF |
| Offset Init | `.workspace/workload.init` | Auto-generated | Single word (0) |

## Workflow Diagram

```
data.bin ──┐
           ├──> convert_bin_to_exe.py ──> .workspace/workload_mem.exe ──┐
text.bin ──┘                              .workspace/workload_ins.exe ──┼──> src/main.py (CPU)
                                          .workspace/workload.init ─────┘
```

## Troubleshooting Quick Fixes

### File size not multiple of 4
**Fix**: Script auto-pads with zeros

### Wrong endianness
**Fix**: Use `'<I'` for little-endian, `'>I'` for big-endian

### .workspace doesn't exist
**Fix**: Script creates it automatically

### Permission denied
**Fix**: `chmod +x convert_bin_to_exe.py`

## RISC-V Instruction Examples

| Instruction | Encoding | Description |
|-------------|----------|-------------|
| NOP | `0x00000013` | No operation (addi x0,x0,0) |
| ADDI x1,x0,1 | `0x00100093` | x1 = 1 |
| ADDI x2,x0,2 | `0x00200113` | x2 = 2 |
| ADD x3,x1,x2 | `0x002081B3` | x3 = x1 + x2 |
| SUB x4,x1,x2 | `0x40208233` | x4 = x1 - x2 |

## Python Struct Format Codes

| Code | Type | Size | Byte Order |
|------|------|------|------------|
| `<I` | unsigned int | 4 bytes | Little-endian |
| `>I` | unsigned int | 4 bytes | Big-endian |
| `<H` | unsigned short | 2 bytes | Little-endian |
| `<B` | unsigned char | 1 byte | N/A |

## Common Patterns

### Fill memory with sequence
```python
import struct
with open('data.bin', 'wb') as f:
    for i in range(256):
        f.write(struct.pack('<I', i))
```

### Fill memory with constant
```python
import struct
with open('data.bin', 'wb') as f:
    for _ in range(256):
        f.write(struct.pack('<I', 0xDEADBEEF))
```

### Generate NOP instructions
```python
import struct
with open('text.bin', 'wb') as f:
    for _ in range(256):
        f.write(struct.pack('<I', 0x00000013))
```

### Read binary file as hex
```bash
hexdump -C data.bin
xxd data.bin
```

### Convert hex to binary (manual)
```bash
echo "12345678" | xxd -r -p > data.bin
```

## Directory Structure After Conversion

```
Assassyn-CPU/
├── main_test/
│   ├── data.bin              (your input)
│   ├── text.bin              (your input)
│   ├── convert_bin_to_exe.py (tool)
│   ├── verify_conversion.py  (tool)
│   └── *.md                  (documentation)
└── .workspace/               (generated)
    ├── workload_mem.exe      (output - data)
    ├── workload_ins.exe      (output - instructions)
    └── workload.init         (output - offset)
```

## Next Steps After Initialization

1. **Run tests**:
   ```bash
   pytest tests/ -v
   ```

2. **Build CPU**:
   ```bash
   python src/main.py
   ```

3. **Modify and test**:
   - Edit `data.bin` or `text.bin`
   - Run `convert_bin_to_exe.py`
   - Run `verify_conversion.py`
   - Test with CPU

## Links to Detailed Documentation

- **中文详细报告**: [初始化报告.md](初始化报告.md)
- **English Report**: [INITIALIZATION_REPORT.md](INITIALIZATION_REPORT.md)
- **Quick Start**: [README.md](README.md)

---

**For help**: See the detailed reports or raise an issue on GitHub
