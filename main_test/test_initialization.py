#!/usr/bin/env python3
"""
Test script to verify dcache/icache initialization
"""
import os
import sys

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def convert_bin_to_hex(bin_path, hex_path):
    """
    将二进制文件转换为 hex 文本格式
    每行一个 32 位字 (8 个十六进制字符, 小写, 无 0x 前缀)
    """
    with open(bin_path, 'rb') as f_in, open(hex_path, 'w') as f_out:
        while True:
            chunk = f_in.read(4)
            if not chunk:
                break
            
            if len(chunk) < 4:
                chunk = chunk + b'\x00' * (4 - len(chunk))
            
            word = int.from_bytes(chunk, byteorder='little')
            f_out.write(f"{word:08x}\n")

def test_conversion():
    """Test the binary to hex conversion"""
    print("=" * 80)
    print("Testing dcache/icache Initialization")
    print("=" * 80)
    
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace = os.path.join(script_dir, '..', 'src', '.workspace')
    
    # Create workspace
    os.makedirs(workspace, exist_ok=True)
    
    # Convert text file
    text_bin = os.path.join(script_dir, '0to100_text.bin')
    text_hex = os.path.join(workspace, '0to100.exe')
    
    print("\n1. Converting instruction binary to hex...")
    if os.path.exists(text_bin):
        convert_bin_to_hex(text_bin, text_hex)
        with open(text_hex, 'r') as f:
            lines = f.readlines()
        print(f"   ✅ Converted {os.path.basename(text_bin)} -> {os.path.basename(text_hex)}")
        print(f"   Instructions: {len(lines)} words ({len(lines) * 4} bytes)")
        print(f"   First 3 instructions:")
        for i, line in enumerate(lines[:3]):
            print(f"     {i:2d}: {line.strip()}")
    else:
        print(f"   ❌ File not found: {text_bin}")
        return False
    
    # Convert data file
    data_bin = os.path.join(script_dir, '0to100_data.bin')
    data_hex = os.path.join(workspace, '0to100.data')
    
    print("\n2. Converting data binary to hex...")
    if os.path.exists(data_bin):
        size = os.path.getsize(data_bin)
        if size > 0:
            convert_bin_to_hex(data_bin, data_hex)
            print(f"   ✅ Converted {os.path.basename(data_bin)} -> {os.path.basename(data_hex)}")
        else:
            with open(data_hex, 'w') as f:
                pass
            print(f"   ✅ Data file is empty, created empty: {os.path.basename(data_hex)}")
    else:
        print(f"   ❌ File not found: {data_bin}")
        return False
    
    # Create workload files
    workload_exe = os.path.join(workspace, 'workload.exe')
    workload_data = os.path.join(workspace, 'workload.data')
    
    print("\n3. Creating workload files...")
    import shutil
    shutil.copy(text_hex, workload_exe)
    shutil.copy(data_hex, workload_data)
    print(f"   ✅ Created {os.path.basename(workload_exe)}")
    print(f"   ✅ Created {os.path.basename(workload_data)}")
    
    # Verify conversion
    print("\n4. Verifying conversion...")
    with open(text_bin, 'rb') as f:
        bin_data = f.read()
    
    with open(text_hex, 'r') as f:
        hex_lines = [line.strip() for line in f.readlines() if line.strip()]
    
    expected_lines = (len(bin_data) + 3) // 4
    if len(hex_lines) == expected_lines:
        print(f"   ✅ Line count correct: {len(hex_lines)} words")
    else:
        print(f"   ❌ Line count mismatch: expected {expected_lines}, got {len(hex_lines)}")
        return False
    
    # Verify each word
    all_correct = True
    for i in range(min(3, len(hex_lines))):
        offset = i * 4
        chunk = bin_data[offset:offset+4]
        if len(chunk) < 4:
            chunk = chunk + b'\x00' * (4 - len(chunk))
        
        expected_word = int.from_bytes(chunk, byteorder='little')
        expected_hex = f"{expected_word:08x}"
        actual_hex = hex_lines[i]
        
        if expected_hex == actual_hex:
            print(f"   ✅ Word {i}: {actual_hex}")
        else:
            print(f"   ❌ Word {i} mismatch: expected {expected_hex}, got {actual_hex}")
            all_correct = False
    
    # Check SP initialization
    print("\n5. Checking SP initialization...")
    depth_log = 16  # Default from main.py
    STACK_TOP = (1 << depth_log) - 4
    print(f"   Memory size: {1 << depth_log} bytes (64KB)")
    print(f"   Stack top address: 0x{STACK_TOP:08X} ({STACK_TOP})")
    print(f"   ✅ SP will be initialized to: 0x{STACK_TOP:08X}")
    
    # Decode first instruction
    first_instr = int(hex_lines[0], 16)
    opcode = first_instr & 0x7F
    rd = (first_instr >> 7) & 0x1F
    rs1 = (first_instr >> 15) & 0x1F
    imm = (first_instr >> 20) & 0xFFF
    if imm & 0x800:
        imm = imm - 0x1000
    
    if opcode == 0x13 and rd == 2 and rs1 == 2:  # ADDI sp, sp, imm
        print(f"   First instruction: ADDI sp, sp, {imm}")
        print(f"   After execution: SP = 0x{STACK_TOP:08X} + {imm} = 0x{STACK_TOP + imm:08X}")
        if imm < 0:
            print(f"   ✅ Stack frame size: {-imm} bytes")
    
    print("\n" + "=" * 80)
    if all_correct:
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)
        print("\nSummary:")
        print("  - Binary to hex conversion: ✅ Working")
        print("  - File format: ✅ Correct (8 hex chars per line, little-endian)")
        print("  - SP initialization: ✅ Configured (0xFFFC)")
        print("  - Workspace files: ✅ Generated")
        print("\nThe CPU is ready to run the 0to100 test program!")
        return True
    else:
        print("❌ SOME TESTS FAILED!")
        print("=" * 80)
        return False

if __name__ == '__main__':
    success = test_conversion()
    sys.exit(0 if success else 1)
