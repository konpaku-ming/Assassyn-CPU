#!/usr/bin/env python3
"""
Extract and display the final value of a register from a CPU simulation log.
"""

import re
import sys

def get_register_history(log_file, register):
    """
    Extract all write operations to a specific register from the log.
    
    Args:
        log_file: Path to the log file
        register: Register name (e.g., 'x10', 'a0')
    
    Returns:
        List of (cycle, value) tuples
    """
    # Map a0-a7 to x10-x17, t0-t6 to x5-x7, x28-x31, etc.
    reg_map = {
        'a0': 'x10', 'a1': 'x11', 'a2': 'x12', 'a3': 'x13',
        'a4': 'x14', 'a5': 'x15', 'a6': 'x16', 'a7': 'x17',
        't0': 'x5', 't1': 'x6', 't2': 'x7',
        's0': 'x8', 's1': 'x9',
        'zero': 'x0', 'ra': 'x1', 'sp': 'x2', 'gp': 'x3', 'tp': 'x4',
    }
    
    # Convert register alias to x-form if needed
    if register in reg_map:
        register = reg_map[register]
    
    with open(log_file, 'r') as f:
        content = f.read()
    
    # Find all writes to the specified register
    pattern = rf'Cycle @(\d+\.\d+):.*WB: Write {register} <= (0x[0-9a-f]+)'
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
    
    print(f"Register Write History (showing last 10 writes):")
    print("=" * 70)
    
    # Show last 10 writes
    for cycle, value in writes[-10:]:
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
