#!/usr/bin/env python3
"""
Verification script to ensure binary to .exe conversion is correct

This script reads the original .bin files and the generated .exe files
and verifies that they match.
"""

import struct
import sys
import os


def verify_conversion(bin_file, exe_file, name):
    """
    Verify that a binary file was correctly converted to an exe file.
    
    Args:
        bin_file: Path to the original .bin file
        exe_file: Path to the generated .exe file
        name: Description name for logging
    
    Returns:
        True if verification passed, False otherwise
    """
    try:
        # Read binary file
        with open(bin_file, 'rb') as f:
            bin_data = f.read()
        
        # Apply same padding logic as conversion script
        # This ensures verification matches conversion behavior
        # Note: This logic is intentionally duplicated from convert_bin_to_exe.py
        # to keep this verification script self-contained and independently runnable
        if len(bin_data) % 4 != 0:
            padding = 4 - (len(bin_data) % 4)
            bin_data += b'\x00' * padding
        
        # Read exe file
        with open(exe_file, 'r') as f:
            exe_lines = f.readlines()
        
        # Parse binary data into 32-bit words (same as conversion script)
        num_words = len(bin_data) // 4
        bin_words = []
        for i in range(num_words):
            word_bytes = bin_data[i*4:(i+1)*4]
            word = struct.unpack('<I', word_bytes)[0]  # Little-endian
            bin_words.append(word)
        
        # Parse exe data
        exe_words = []
        for line in exe_lines:
            line = line.strip()
            if line:  # Skip empty lines
                exe_words.append(int(line, 16))
        
        # Verify counts match
        if len(bin_words) != len(exe_words):
            print(f"❌ {name}: Word count mismatch!")
            print(f"   Binary file: {len(bin_words)} words")
            print(f"   Exe file: {len(exe_words)} words")
            return False
        
        # Verify each word
        mismatches = []
        for i in range(len(bin_words)):
            if bin_words[i] != exe_words[i]:
                mismatches.append((i, bin_words[i], exe_words[i]))
        
        if mismatches:
            print(f"❌ {name}: Found {len(mismatches)} mismatches!")
            for addr, bin_val, exe_val in mismatches[:5]:  # Show first 5
                print(f"   Word {addr}: 0x{bin_val:08x} (bin) != 0x{exe_val:08x} (exe)")
            return False
        
        print(f"✅ {name}: Verification passed! ({len(bin_words)} words)")
        
        # Show first few values for confirmation
        if len(bin_words) > 0:
            print(f"   First few values: ", end="")
            for i in range(min(4, len(bin_words))):
                print(f"0x{bin_words[i]:08x} ", end="")
            print()
        
        return True
        
    except FileNotFoundError as e:
        print(f"❌ {name}: File not found - {e}")
        return False
    except Exception as e:
        print(f"❌ {name}: Error during verification - {e}")
        return False


def main():
    """Main verification process"""
    print("=" * 70)
    print("Assassyn CPU Memory Initialization - Verification")
    print("=" * 70)
    print()
    
    # Define file paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.join(os.path.dirname(script_dir), '.workspace')
    
    data_bin = os.path.join(script_dir, 'accumulate_data.bin')
    text_bin = os.path.join(script_dir, 'accumulate_text.bin')
    data_exe = os.path.join(workspace_dir, 'workload_mem.exe')
    text_exe = os.path.join(workspace_dir, 'workload_ins.exe')
    
    # Check if files exist
    if not os.path.exists(data_bin):
        print(f"❌ Error: {data_bin} not found")
        return 1
    
    if not os.path.exists(text_bin):
        print(f"❌ Error: {text_bin} not found")
        return 1
    
    if not os.path.exists(data_exe) or not os.path.exists(text_exe):
        print("❌ Error: .exe files not found in .workspace/")
        print("   Please run convert_bin_to_exe.py first")
        return 1
    
    # Verify conversions
    success1 = verify_conversion(
        data_bin,
        data_exe,
        "Data Memory (accumulate_data.bin → workload_mem.exe)"
    )
    print()
    
    success2 = verify_conversion(
        text_bin,
        text_exe,
        "Instruction Memory (accumulate_text.bin → workload_ins.exe)"
    )
    print()
    
    # Summary
    print("=" * 70)
    if success1 and success2:
        print("✅ All verifications passed!")
        print()
        print("The memory initialization files are ready for CPU simulation.")
        print("You can now run: python src/main.py")
    else:
        print("❌ Verification failed!")
        print("Please check the error messages above.")
        return 1
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
