#!/usr/bin/env python3
"""
Binary to Assassyn SRAM Initialization File Converter

This script converts raw binary files (data.bin, text.bin) to the format
expected by Assassyn SRAM initialization (.exe files).

The Assassyn SRAM initialization file format is a text file where each line
contains a hexadecimal value representing one memory word (32-bit).

Usage:
    python3 convert_bin_to_exe.py
    
This will:
1. Read data.bin and convert it to workload_mem.exe (for main_memory)
2. Read text.bin and convert it to workload_ins.exe (for icache)
"""

import struct
import sys
import os


def convert_binary_to_exe(input_bin_path, output_exe_path, description):
    """
    Convert a binary file to Assassyn SRAM initialization format.
    
    Args:
        input_bin_path: Path to input .bin file
        output_exe_path: Path to output .exe file
        description: Description of what's being converted (for logging)
    """
    try:
        # Read binary file
        with open(input_bin_path, 'rb') as f:
            binary_data = f.read()
        
        # Calculate number of 32-bit words
        num_bytes = len(binary_data)
        if num_bytes % 4 != 0:
            print(f"⚠️  Warning: {input_bin_path} size ({num_bytes} bytes) is not a multiple of 4")
            print(f"    Padding with zeros to align to 32-bit words")
            # Pad with zeros to ensure 4-byte alignment
            # Note: Zero-padding at the end is safe for both data and instructions
            # - For data: Extra zeros won't be accessed if program stays within bounds
            # - For instructions: Extra NOPs (0x00000000) or unreachable code
            padding = 4 - (num_bytes % 4)
            binary_data += b'\x00' * padding
            num_bytes = len(binary_data)
        
        num_words = num_bytes // 4
        
        # Parse 32-bit words (little-endian)
        words = []
        for i in range(num_words):
            word_bytes = binary_data[i*4:(i+1)*4]
            word = struct.unpack('<I', word_bytes)[0]  # Little-endian unsigned int
            words.append(word)
        
        # Write to .exe file (one hex value per line, no 0x prefix)
        with open(output_exe_path, 'w') as f:
            for word in words:
                # Format as 8-digit hex (padded with zeros)
                f.write(f"{word:08x}\n")
        
        print(f"✅ Converted {description}:")
        print(f"   Input:  {input_bin_path} ({num_bytes} bytes, {num_words} words)")
        print(f"   Output: {output_exe_path}")
        
        # Show first few values for verification
        if num_words > 0:
            print(f"   First few values: ", end="")
            for i in range(min(4, num_words)):
                print(f"0x{words[i]:08x} ", end="")
            print()
        
        return True
        
    except FileNotFoundError:
        print(f"❌ Error: Input file '{input_bin_path}' not found")
        return False
    except Exception as e:
        print(f"❌ Error converting {input_bin_path}: {e}")
        return False


def main():
    """Main conversion process"""
    print("=" * 70)
    print("Assassyn CPU Memory Initialization Converter")
    print("=" * 70)
    print()
    
    # Define file paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.join(os.path.dirname(script_dir), '.workspace')
    
    data_bin = os.path.join(script_dir, 'data.bin')
    text_bin = os.path.join(script_dir, 'text.bin')
    
    # Create workspace directory if it doesn't exist
    os.makedirs(workspace_dir, exist_ok=True)
    print(f"📁 Workspace directory: {workspace_dir}")
    print()
    
    data_exe = os.path.join(workspace_dir, 'workload_mem.exe')
    text_exe = os.path.join(workspace_dir, 'workload_ins.exe')
    
    # Convert data.bin to workload_mem.exe
    success1 = convert_binary_to_exe(
        data_bin, 
        data_exe, 
        "Data Memory (data.bin → workload_mem.exe)"
    )
    print()
    
    # Convert text.bin to workload_ins.exe
    success2 = convert_binary_to_exe(
        text_bin, 
        text_exe, 
        "Instruction Memory (text.bin → workload_ins.exe)"
    )
    print()
    
    # Also create workload.init for the offset initialization
    # This is typically just a single word with value 0
    init_file = os.path.join(workspace_dir, 'workload.init')
    try:
        with open(init_file, 'w') as f:
            f.write("00000000\n")
        print(f"✅ Created initialization file: {init_file}")
    except Exception as e:
        print(f"⚠️  Warning: Could not create {init_file}: {e}")
    
    print()
    print("=" * 70)
    if success1 and success2:
        print("✅ Conversion completed successfully!")
        print()
        print("Next steps:")
        print("1. Verify the generated .exe files in .workspace/")
        print("2. Run your CPU simulation with: python src/main.py")
        print("3. The CPU will automatically load these files during initialization")
    else:
        print("❌ Conversion failed. Please check the error messages above.")
        return 1
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
