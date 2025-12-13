# Assassyn CPU Memory Initialization Report

## Overview

This report describes how to initialize the Assassyn CPU's main memory (main_memory) and instruction cache (icache) using `data.bin` and `text.bin` files.

## File Description

### Input Files

- **`data.bin`**: Data segment binary file
  - Format: Raw binary data
  - Endianness: Little-Endian
  - Word width: 32-bit (4-byte aligned)
  - Purpose: Initialize CPU data memory (main_memory)

- **`text.bin`**: Instruction segment binary file
  - Format: Raw binary instructions
  - Endianness: Little-Endian
  - Word width: 32-bit RISC-V instructions
  - Purpose: Initialize CPU instruction cache (icache)

### Output Files

- **`.workspace/workload_mem.exe`**: Data memory initialization file
  - Format: ASCII hexadecimal text
  - One 32-bit word per line (8 hex digits)
  - Converted from `data.bin`

- **`.workspace/workload_ins.exe`**: Instruction memory initialization file
  - Format: ASCII hexadecimal text
  - One 32-bit instruction per line (8 hex digits)
  - Converted from `text.bin`

- **`.workspace/workload.init`**: Offset initialization file
  - Contains initial offset value (typically 0)

## Initialization Process

### Step 1: Prepare Binary Files

Ensure the following files are in the `main_test/` directory:
- `data.bin` - Data segment
- `text.bin` - Instruction segment

The repository includes example files. You can also create your own:

```python
import struct

# Create example data segment (data.bin)
data_values = [
    0x00000000,  # Address 0
    0x12345678,  # Address 4
    0xDEADBEEF,  # Address 8
    0xCAFEBABE,  # Address 12
]

with open('data.bin', 'wb') as f:
    for value in data_values:
        f.write(struct.pack('<I', value))  # Little-endian 32-bit integer

# Create example instruction segment (text.bin)
instructions = [
    0x00000013,  # addi x0, x0, 0  (NOP)
    0x00100093,  # addi x1, x0, 1
    0x00200113,  # addi x2, x0, 2
    0x002081B3,  # add  x3, x1, x2
]

with open('text.bin', 'wb') as f:
    for instr in instructions:
        f.write(struct.pack('<I', instr))
```

### Step 2: Run Conversion Script

Use the provided conversion script to convert binary files to Assassyn SRAM initialization format:

```bash
cd main_test
python3 convert_bin_to_exe.py
```

#### Conversion Process

The conversion script performs the following operations:

1. **Read binary files**: Read `.bin` files in binary mode
2. **Parse 32-bit words**: Parse each 32-bit word in little-endian format
3. **Generate hexadecimal text**: Convert each word to 8-digit hex (without `0x` prefix)
4. **Write .exe files**: One value per line, saved to `.workspace/` directory
5. **Create directories**: Automatically create `.workspace/` directory if it doesn't exist

#### Expected Output

```
======================================================================
Assassyn CPU Memory Initialization Converter
======================================================================

📁 Workspace directory: /path/to/.workspace

✅ Converted Data Memory (data.bin → workload_mem.exe):
   Input:  data.bin (32 bytes, 8 words)
   Output: .workspace/workload_mem.exe
   First few values: 0x00000000 0x12345678 0xdeadbeef 0xcafebabe 

✅ Converted Instruction Memory (text.bin → workload_ins.exe):
   Input:  text.bin (32 bytes, 8 words)
   Output: .workspace/workload_ins.exe
   First few values: 0x00000013 0x00100093 0x00200113 0x002081b3 

✅ Created initialization file: .workspace/workload.init

======================================================================
✅ Conversion completed successfully!
======================================================================
```

### Step 3: Verify Generated Files

Check the files in the `.workspace/` directory:

```bash
ls -l ../.workspace/
cat ../.workspace/workload_mem.exe
cat ../.workspace/workload_ins.exe
```

#### File Format Examples

**workload_ins.exe** (Instruction memory):
```
00000013
00100093
00200113
002081b3
40208233
002092b3
00312333
0030e3b3
```

**workload_mem.exe** (Data memory):
```
00000000
12345678
deadbeef
cafebabe
00000001
00000002
00000003
ffffffff
```

### Step 4: Run CPU Simulation

After conversion, you can run the CPU simulation directly:

```bash
cd ..
python src/main.py
```

The CPU will automatically load initialization files from:
- Data memory: `.workspace/workload_mem.exe`
- Instruction memory: `.workspace/workload_ins.exe`
- Offset initialization: `.workspace/workload.init`

## CPU Memory Initialization Mechanism

### Initialization Code in main.py

```python
# In the build_cpu() function in src/main.py:

# Data memory initialization
main_memory = SRAM(
    width=32, 
    depth=1 << depth_log, 
    init_file=f"{workspace}/workload_mem.exe"  # Converted from data.bin
)

# Instruction cache initialization
icache = SRAM(
    width=32, 
    depth=1 << depth_log, 
    init_file=f"{workspace}/workload_ins.exe"  # Converted from text.bin
)
```

### Memory Map

- **Address width**: Configurable (default `depth_log=16`, i.e., 2^16 = 64K words)
- **Data width**: 32-bit
- **Address space**:
  - Instruction memory (icache): 0x00000000 - 0x0000FFFF (word addresses)
  - Data memory (main_memory): 0x00000000 - 0x0000FFFF (word addresses)
- **Endianness**: Little-Endian
- **Alignment**: 32-bit word aligned (addresses aligned to 4 bytes)

### SRAM Initialization Mechanism

Assassyn SRAM's `init_file` parameter accepts the following format:
- Plain text file
- One hexadecimal value per line (without `0x` prefix)
- Values correspond to memory addresses 0, 1, 2, ... in order
- Format: `%08x` (8-digit hex with leading zeros)

## File Format Details

### Binary File Format (.bin)

- **Byte order**: Little-endian (LSB first)
- **Data type**: Unsigned 32-bit integer
- **Alignment**: Must be a multiple of 4 bytes

#### Example: Value 0x12345678 in file
```
Offset: 00 01 02 03
Bytes:  78 56 34 12  (little-endian)
```

### Initialization File Format (.exe)

- **Encoding**: ASCII text
- **Line format**: `%08x\n` (8-digit lowercase hex + newline)
- **Number of lines**: Equal to number of memory words
- **Comments**: Not supported

#### Example
```
00000013    # First word (address 0)
00100093    # Second word (address 1)
00200113    # Third word (address 2)
```

## Complete Workflow Example

Here's a complete workflow from source to execution:

```bash
# 1. Enter project directory
cd Assassyn-CPU

# 2. Prepare binary files (generate examples using Python)
cd main_test
python3 << 'EOF'
import struct

# Data segment
with open('data.bin', 'wb') as f:
    for i in range(16):
        f.write(struct.pack('<I', i * 0x1000))

# Instruction segment (NOP instructions)
with open('text.bin', 'wb') as f:
    for i in range(16):
        f.write(struct.pack('<I', 0x00000013))
EOF

# 3. Convert to Assassyn format
python3 convert_bin_to_exe.py

# 4. Verify output
head ../.workspace/workload_mem.exe
head ../.workspace/workload_ins.exe

# 5. Run CPU
cd ..
python src/main.py

# 6. Run tests
pytest tests/test_fetch.py -v
```

## Troubleshooting

### Issue 1: File size not a multiple of 4

**Error**: `.bin` file size is not a multiple of 4 bytes

**Solution**: The conversion script automatically pads with zero bytes. Or manually ensure correct file size:

```python
# Check and pad
import os
size = os.path.getsize('data.bin')
if size % 4 != 0:
    with open('data.bin', 'ab') as f:
        f.write(b'\x00' * (4 - size % 4))
```

### Issue 2: Endianness error

**Symptom**: Data reads incorrectly, values appear reversed

**Cause**: Endianness mismatch

**Solution**:
- CPU uses little-endian
- Ensure using `'<I'` format (little-endian unsigned integer)
- If data is big-endian, use `'>I'` during conversion

### Issue 3: .workspace directory doesn't exist

**Error**: Cannot find `.workspace` directory

**Solution**:
```bash
mkdir -p .workspace
```

Or run the conversion script, which automatically creates the directory.

## Tools and Files

### Provided Tools

- **`convert_bin_to_exe.py`**: Binary to Assassyn format converter
  - Location: `main_test/convert_bin_to_exe.py`
  - Usage: `python3 convert_bin_to_exe.py`
  - Input: `data.bin`, `text.bin`
  - Output: `.workspace/workload_mem.exe`, `.workspace/workload_ins.exe`

### Example Files

- **`data.bin`**: Example data segment (8 words, 32 bytes)
- **`text.bin`**: Example instruction segment (8 instructions, 32 bytes)

### Generated Files

- `.workspace/workload_mem.exe`: Data memory initialization
- `.workspace/workload_ins.exe`: Instruction memory initialization
- `.workspace/workload.init`: Offset initialization

## Advanced Usage

### Loading Large Programs

For larger programs:

```python
# Generate many instructions
instructions = []
for i in range(1024):
    instructions.append(0x00000013)  # NOP

with open('text.bin', 'wb') as f:
    for instr in instructions:
        f.write(struct.pack('<I', instr))
```

### Extracting from ELF Files

```bash
# Use objcopy to extract sections
riscv32-unknown-elf-objcopy -O binary --only-section=.text program.elf text.bin
riscv32-unknown-elf-objcopy -O binary --only-section=.data program.elf data.bin
```

### Verification Script

```python
# Verify conversion after processing
def verify_conversion(bin_file, exe_file):
    import struct
    
    # Read original binary
    with open(bin_file, 'rb') as f:
        bin_data = f.read()
    
    # Read converted hex
    with open(exe_file, 'r') as f:
        exe_data = [int(line.strip(), 16) for line in f]
    
    # Compare
    for i in range(len(bin_data) // 4):
        orig = struct.unpack('<I', bin_data[i*4:(i+1)*4])[0]
        conv = exe_data[i]
        assert orig == conv, f"Mismatch at word {i}: {orig:08x} != {conv:08x}"
    
    print(f"✅ Verification passed for {bin_file}")

verify_conversion('data.bin', '../.workspace/workload_mem.exe')
verify_conversion('text.bin', '../.workspace/workload_ins.exe')
```

## Reference

### Related Files
- `src/main.py` - CPU building and memory initialization
- `src/fetch.py` - Instruction fetching (icache access)
- `src/memory.py` - Data access (main_memory access)
- `tests/common.py` - Test utilities and SRAM initialization helpers

### RISC-V Instruction Format
- RV32I base instruction set
- 32-bit instruction words
- Little-endian encoding

### Assassyn Documentation
- Assassyn HDL syntax
- SRAM module usage
- Simulator configuration

## Summary

Using the methods provided in this report, you can:

1. ✅ Initialize data memory (main_memory) using `data.bin`
2. ✅ Initialize instruction cache (icache) using `text.bin`
3. ✅ Automatically convert binary files to Assassyn SRAM format
4. ✅ Verify and debug memory initialization process
5. ✅ Run complete CPU simulation

Key Files:
- **Input**: `main_test/data.bin`, `main_test/text.bin`
- **Conversion tool**: `main_test/convert_bin_to_exe.py`
- **Output**: `.workspace/workload_mem.exe`, `.workspace/workload_ins.exe`
- **Usage**: `python src/main.py` automatically loads these files

---

**Report Generated**: 2025-12-13  
**CPU Architecture**: RV32I 5-stage pipeline  
**HDL**: Assassyn  
**Tool Version**: Python 3.10+
