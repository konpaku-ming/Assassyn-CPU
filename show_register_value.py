#!/usr/bin/env python3
"""
Extract and display the final value of a register from a CPU simulation log.
"""

import re
import sys

# Configuration
RECENT_WRITES_DISPLAY = 10  # Number of recent writes to display

def get_register_history(log_file, register):
    """
    Extract all write operations to a specific register from the log.
    
    Args:
        log_file: Path to the log file
        register: Register name (e.g., 'x10', 'a0')
    
    Returns:
        List of (cycle, value) tuples
    """
    # Complete RISC-V ABI register name mapping
    reg_map = {
        # Argument/return registers
        'a0': 'x10', 'a1': 'x11', 'a2': 'x12', 'a3': 'x13',
        'a4': 'x14', 'a5': 'x15', 'a6': 'x16', 'a7': 'x17',
        # Temporary registers
        't0': 'x5', 't1': 'x6', 't2': 'x7',
        't3': 'x28', 't4': 'x29', 't5': 'x30', 't6': 'x31',
        # Saved registers
        's0': 'x8', 's1': 'x9', 's2': 'x18', 's3': 'x19',
        's4': 'x20', 's5': 'x21', 's6': 'x22', 's7': 'x23',
        's8': 'x24', 's9': 'x25', 's10': 'x26', 's11': 'x27',
        # Special purpose registers
        'zero': 'x0', 'ra': 'x1', 'sp': 'x2', 'gp': 'x3', 'tp': 'x4',
        'fp': 'x8',  # Frame pointer (alias for s0)
    }
    
    # Convert register alias to x-form if needed
    if register in reg_map:
        register = reg_map[register]
    
    with open(log_file, 'r') as f:
        content = f.read()
    
    # Use more specific pattern with word boundaries for efficiency
    pattern = rf'\bCycle @(\d+\.\d+):.*\bWB: Write {register} <= (0x[0-9a-f]+)'
    writes = re.findall(pattern, content)
    
    return writes

def parse_value(hex_val):
    """Parse hex value as signed 32-bit integer"""
    val = int(hex_val, 16)
    # Convert to signed if needed
    if val >= 0x80000000:
        val = val - 0x100000000
    return val

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 show_register_value.py <register> [log_file]")
        print()
        print("Examples:")
        print("  python3 show_register_value.py a0")
        print("  python3 show_register_value.py x10 logs/0to100.log")
        print("  python3 show_register_value.py x15")
        print()
        print("Register names: x0-x31, or aliases like a0, a1, t0, s0, etc.")
        return 1
    
    register = sys.argv[1]
    log_file = sys.argv[2] if len(sys.argv) > 2 else "logs/0to100.log"
    
    print(f"Analyzing register '{register}' in {log_file}...")
    print()
    
    writes = get_register_history(log_file, register)
    
    if not writes:
        print(f"❌ No write operations found for register '{register}'")
        return 1
    
    print(f"Register Write History (showing last {RECENT_WRITES_DISPLAY} writes):")
    print("=" * 70)
    
    # Show last N writes
    for cycle, value in writes[-RECENT_WRITES_DISPLAY:]:
        decimal = parse_value(value)
        print(f"  Cycle {cycle:>7}: {value} (decimal: {decimal})")
    
    print("=" * 70)
    print()
    
    # Show final value
    final_cycle, final_value = writes[-1]
    final_decimal = parse_value(final_value)
    
    print(f"📊 Summary:")
    print(f"  Total writes: {len(writes)}")
    print(f"  Final value:  {final_value} (decimal: {final_decimal})")
    print(f"  Final cycle:  {final_cycle}")
    
    # Check if it's the return value (a0)
    if register in ['a0', 'x10']:
        print()
        print(f"  ℹ️  Register a0/x10 is typically used for function return values")
        if final_decimal == 0:
            print(f"     The program returned 0 (success)")
        else:
            print(f"     The program returned {final_decimal}")
    
    return 0

if __name__ == "__main__":
    exit(main())
