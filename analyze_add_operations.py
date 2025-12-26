#!/usr/bin/env python3
"""
Analyze ADD operations in the 0to100.log file to verify operand correctness.
This script extracts all ADD operations and checks if Op1 + Op2 = Result.
"""

import re
import sys
from typing import List, Dict, Tuple

# Constants for search ranges
BACKWARD_SEARCH_LINES = 10  # Number of lines to search backwards for operands
FORWARD_SEARCH_LINES = 5    # Number of lines to search forward for results

def parse_hex(value: str) -> int:
    """Parse hexadecimal value, handling signed 32-bit representation"""
    num = int(value, 16)
    # Convert to signed 32-bit if needed
    if num >= 0x80000000:
        num = num - 0x100000000
    return num

def extract_add_operations(log_file: str) -> List[Dict]:
    """
    Extract all ADD operations from the log file with their operands and results.
    """
    add_operations = []
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for ADD operation marker
        if "EX: ALU Operation: ADD" in line:
            # Extract cycle number
            cycle_match = re.search(r'Cycle @(\d+\.\d+)', line)
            cycle = cycle_match.group(1) if cycle_match else "unknown"
            
            # Look backwards for operands (Op1 and Op2)
            op1 = None
            op2 = None
            result = None
            op1_source = None
            op2_source = None
            
            # Search backwards for operand information
            for j in range(max(0, i - BACKWARD_SEARCH_LINES), i):
                prev_line = lines[j]
                
                # Extract Op1
                if "EX: ALU Op1 source:" in prev_line:
                    op1_match = re.search(r'source: (\w+) \((0x[0-9a-f]+)\)', prev_line)
                    if op1_match:
                        op1_source = op1_match.group(1)
                        op1 = op1_match.group(2)
                
                # Extract Op2
                if "EX: ALU Op2 source:" in prev_line:
                    op2_match = re.search(r'source: (\w+) \((0x[0-9a-f]+)\)', prev_line)
                    if op2_match:
                        op2_source = op2_match.group(1)
                        op2 = op2_match.group(2)
            
            # Look forward for result
            for j in range(i + 1, min(len(lines), i + FORWARD_SEARCH_LINES)):
                next_line = lines[j]
                if "EX: ALU Result:" in next_line:
                    result_match = re.search(r'Result: (0x[0-9a-f]+)', next_line)
                    if result_match:
                        result = result_match.group(1)
                    break
            
            if op1 and op2 and result:
                add_operations.append({
                    'cycle': cycle,
                    'op1': op1,
                    'op2': op2,
                    'result': result,
                    'op1_source': op1_source,
                    'op2_source': op2_source,
                    'line_num': i + 1
                })
        
        i += 1
    
    return add_operations

def verify_add_operations(operations: List[Dict]) -> Tuple[int, int, List[Dict]]:
    """
    Verify that each ADD operation is correct: Op1 + Op2 = Result
    Returns: (correct_count, incorrect_count, incorrect_operations)
    """
    correct = 0
    incorrect = 0
    incorrect_ops = []
    
    for op in operations:
        op1_val = parse_hex(op['op1'])
        op2_val = parse_hex(op['op2'])
        result_val = parse_hex(op['result'])
        
        # Compute expected result (with 32-bit wraparound)
        expected = (op1_val + op2_val) & 0xFFFFFFFF
        # Convert to signed if needed
        if expected >= 0x80000000:
            expected = expected - 0x100000000
        
        # Convert result to signed for comparison
        actual = result_val
        
        if expected == actual:
            correct += 1
            op['status'] = 'CORRECT'
        else:
            incorrect += 1
            op['status'] = 'INCORRECT'
            op['expected'] = hex(expected & 0xFFFFFFFF)
            op['op1_decimal'] = op1_val
            op['op2_decimal'] = op2_val
            op['expected_decimal'] = expected
            op['actual_decimal'] = actual
            incorrect_ops.append(op)
    
    return correct, incorrect, incorrect_ops

def generate_report(operations: List[Dict], correct: int, incorrect: int, incorrect_ops: List[Dict]) -> str:
    """Generate analysis report"""
    report = []
    report.append("=" * 80)
    report.append("ADD Operations Analysis Report for 0to100.log")
    report.append("=" * 80)
    report.append("")
    report.append(f"Total ADD operations found: {len(operations)}")
    report.append(f"Correct operations: {correct}")
    report.append(f"Incorrect operations: {incorrect}")
    report.append("")
    
    if incorrect > 0:
        report.append("⚠️  INCORRECT OPERATIONS DETECTED:")
        report.append("=" * 80)
        for op in incorrect_ops:
            report.append(f"\nCycle: {op['cycle']} (Line {op['line_num']})")
            report.append(f"  Op1: {op['op1']} (decimal: {op['op1_decimal']}) from {op['op1_source']}")
            report.append(f"  Op2: {op['op2']} (decimal: {op['op2_decimal']}) from {op['op2_source']}")
            report.append(f"  Expected Result: {op['expected']} (decimal: {op['expected_decimal']})")
            report.append(f"  Actual Result:   {op['result']} (decimal: {op['actual_decimal']})")
            report.append(f"  ❌ ERROR: {op['op1']} + {op['op2']} should equal {op['expected']}, but got {op['result']}")
    else:
        report.append("✅ ALL ADD OPERATIONS ARE CORRECT!")
        report.append("")
        report.append("Sample ADD operations:")
        for i, op in enumerate(operations[:10]):
            op1_val = parse_hex(op['op1'])
            op2_val = parse_hex(op['op2'])
            result_val = parse_hex(op['result'])
            report.append(f"  Cycle {op['cycle']}: {op['op1']} ({op1_val}) + {op['op2']} ({op2_val}) = {op['result']} ({result_val}) ✓")
    
    report.append("")
    report.append("=" * 80)
    report.append("Analysis Complete")
    report.append("=" * 80)
    
    return "\n".join(report)

def main():
    # Allow command line argument for log file path
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("Usage: python3 analyze_add_operations.py [log_file_path]")
            print()
            print("Analyzes ADD operations in a CPU simulation log file.")
            print()
            print("Arguments:")
            print("  log_file_path    Path to the log file (default: logs/0to100.log)")
            print()
            print("Examples:")
            print("  python3 analyze_add_operations.py")
            print("  python3 analyze_add_operations.py logs/0to100.log")
            print("  python3 analyze_add_operations.py logs/mul1to10.log")
            return 0
        log_file = sys.argv[1]
    else:
        log_file = "logs/0to100.log"
    
    print(f"Analyzing ADD operations in {log_file}...")
    print()
    
    # Extract ADD operations
    operations = extract_add_operations(log_file)
    print(f"Found {len(operations)} ADD operations")
    
    # Verify operations
    correct, incorrect, incorrect_ops = verify_add_operations(operations)
    
    # Generate report
    report = generate_report(operations, correct, incorrect, incorrect_ops)
    
    # Print report to console
    print(report)
    
    # Save report to file
    report_file = "ADD_OPERATIONS_ANALYSIS.md"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\nReport saved to: {report_file}")
    
    # Return exit code based on correctness
    return 0 if incorrect == 0 else 1

if __name__ == "__main__":
    exit(main())
