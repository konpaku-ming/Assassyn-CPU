#!/usr/bin/env python3
"""
Verify the correctness of the 0-to-100 accumulation program.
This script checks if the program correctly computes the sum 0+1+2+...+100 = 5050.
"""

import re
import sys

def analyze_accumulation(log_file):
    """
    Analyze the 0to100 program execution to verify the accumulation result.
    
    Expected behavior:
    - Load 101 values (0 through 100) from memory
    - Accumulate them: sum = 0 + 1 + 2 + ... + 100
    - Expected result: 5050
    """
    
    with open(log_file, 'r') as f:
        content = f.read()
    
    # Extract all memory load operations
    loads = re.findall(r'MEM: OP LOAD.*?MEM: Bypass <= (0x[0-9a-f]+)', content, re.DOTALL)
    
    # Extract values loaded
    loaded_values = []
    for val_hex in loads:
        val = int(val_hex, 16)
        if val >= 0x80000000:
            val = val - 0x100000000
        loaded_values.append(val)
    
    # Find all register writes to identify the accumulator
    all_reg_final_values = {}
    for i in range(32):
        reg = f'x{i}'
        writes = re.findall(rf'Cycle @(\d+\.\d+):.*WB: Write {reg} <= (0x[0-9a-f]+)', content)
        if writes:
            last_cycle, last_val = writes[-1]
            decimal = int(last_val, 16)
            if decimal >= 0x80000000:
                decimal = decimal - 0x100000000
            all_reg_final_values[reg] = (decimal, last_val, last_cycle, len(writes))
    
    # Expected sum
    expected_sum = sum(range(101))  # 0 + 1 + 2 + ... + 100
    actual_sum_from_loads = sum(loaded_values)
    
    # Generate report
    print("=" * 80)
    print("0-to-100 Accumulation Analysis Report")
    print("=" * 80)
    print()
    
    print("📊 Program Analysis:")
    print(f"  Memory loads: {len(loaded_values)}")
    print(f"  Loaded values: {loaded_values[:10]}{'...' if len(loaded_values) > 10 else ''}")
    print()
    
    print("🎯 Expected Behavior:")
    print(f"  Should load: 0, 1, 2, 3, ..., 100")
    print(f"  Should compute: 0 + 1 + 2 + ... + 100 = {expected_sum}")
    print()
    
    print("📈 Actual Behavior:")
    print(f"  Actually loaded: {loaded_values[:5]}{'...' if len(loaded_values) > 5 else ''}")
    print(f"  Sum of loaded values: {actual_sum_from_loads}")
    print()
    
    # Check correctness
    print("✓/✗ Verification Results:")
    print("-" * 80)
    
    # Check 1: Number of loads
    if len(loaded_values) == 101:
        print(f"  ✓ Correct number of loads: {len(loaded_values)} (expected 101)")
    else:
        print(f"  ✗ Incorrect number of loads: {len(loaded_values)} (expected 101)")
    
    # Check 2: Loaded values
    expected_values = list(range(101))
    if loaded_values == expected_values:
        print(f"  ✓ Loaded values are correct: 0, 1, 2, ..., 100")
    else:
        print(f"  ✗ Loaded values are INCORRECT!")
        print(f"    Expected: {expected_values[:10]}...")
        print(f"    Actual:   {loaded_values[:10]}...")
        if all(v == 0 for v in loaded_values):
            print(f"    ⚠️  All loaded values are 0 - memory array not initialized!")
    
    # Check 3: Find accumulator register
    print()
    print("  Checking for accumulation result in registers...")
    
    found_correct_sum = False
    for reg, (val, hex_val, cycle, writes) in all_reg_final_values.items():
        if val == expected_sum:
            print(f"  ✓ Register {reg} contains correct sum: {hex_val} (decimal: {val})")
            found_correct_sum = True
        elif val == actual_sum_from_loads and actual_sum_from_loads != expected_sum:
            print(f"  ⚠️  Register {reg} contains sum of loaded values: {hex_val} (decimal: {val})")
            print(f"      (This matches sum of actual loaded values, but not expected sum)")
    
    if not found_correct_sum:
        print(f"  ✗ No register contains the expected sum ({expected_sum})")
        print()
        print("  Final register values (non-zero or significant):")
        for reg, (val, hex_val, cycle, writes) in sorted(all_reg_final_values.items()):
            if val != 0 or reg == 'x10':
                print(f"    {reg}: {hex_val} (decimal: {val}) at cycle {cycle}, {writes} writes")
    
    print()
    print("=" * 80)
    print("🔍 CONCLUSION:")
    print("=" * 80)
    
    if found_correct_sum:
        print("✅ CORRECT: The program computed the sum 0+1+2+...+100 = 5050 correctly!")
    elif actual_sum_from_loads == 0 and all(v == 0 for v in loaded_values):
        print("❌ INCORRECT: The program computed sum = 0, but expected 5050")
        print()
        print("🔴 ROOT CAUSE:")
        print("   The memory array contains all zeros instead of 0, 1, 2, ..., 100")
        print("   The program logic is correct (it performs the loads and accumulation),")
        print("   but the input data is wrong!")
        print()
        print("💡 RECOMMENDATION:")
        print("   Initialize the memory array with values 0 through 100 before")
        print("   running the program, or generate the sequence in the program itself.")
    else:
        print(f"❌ INCORRECT: Expected sum = {expected_sum}, but got {actual_sum_from_loads}")
    
    print("=" * 80)
    print()
    
    return found_correct_sum

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("Usage: python3 verify_accumulation.py [log_file]")
            print()
            print("Verifies that the 0-to-100 accumulation program produces the correct result.")
            print()
            print("Arguments:")
            print("  log_file    Path to the log file (default: logs/0to100.log)")
            print()
            print("The program should compute: 0 + 1 + 2 + ... + 100 = 5050")
            return 0
        log_file = sys.argv[1]
    else:
        log_file = "logs/0to100.log"
    
    print(f"Analyzing accumulation in {log_file}...")
    print()
    
    result = analyze_accumulation(log_file)
    
    return 0 if result else 1

if __name__ == "__main__":
    exit(main())
