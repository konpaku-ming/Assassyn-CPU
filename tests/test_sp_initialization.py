#!/usr/bin/env python3
"""
Unit test to verify the stack pointer initialization fix.

This test validates that the stack pointer (SP) is correctly calculated
to be within the addressable range of the dcache for various depth_log values.
"""

def calculate_sp(depth_log):
    """Calculate the stack pointer value for a given cache depth."""
    return ((1 << depth_log) - 1) * 4

def test_sp_initialization():
    """Test stack pointer initialization for various cache depths."""
    
    test_cases = [
        # (depth_log, expected_num_words, expected_max_byte_addr, expected_sp)
        (16, 65536, 262140, 0x3FFFC),   # 64K words = 256KB - 4 bytes
        (14, 16384, 65532, 0xFFFC),     # 16K words = 64KB - 4 bytes
        (12, 4096, 16380, 0x3FFC),      # 4K words = 16KB - 4 bytes
        (10, 1024, 4092, 0xFFC),        # 1K words = 4KB - 4 bytes
    ]
    
    all_passed = True
    
    for depth_log, expected_words, expected_max_addr, expected_sp in test_cases:
        # Calculate values
        num_words = 1 << depth_log
        max_byte_addr = (num_words - 1) * 4
        sp = calculate_sp(depth_log)
        
        # Verify calculations
        passed = True
        errors = []
        
        if num_words != expected_words:
            passed = False
            errors.append(f"  ✗ Words: expected {expected_words}, got {num_words}")
        else:
            errors.append(f"  ✓ Words: {num_words}")
            
        if max_byte_addr != expected_max_addr:
            passed = False
            errors.append(f"  ✗ Max address: expected 0x{expected_max_addr:X}, got 0x{max_byte_addr:X}")
        else:
            errors.append(f"  ✓ Max address: 0x{max_byte_addr:X}")
            
        if sp != expected_sp:
            passed = False
            errors.append(f"  ✗ SP: expected 0x{expected_sp:X}, got 0x{sp:X}")
        else:
            errors.append(f"  ✓ SP: 0x{sp:X}")
        
        # Check SP is within valid range
        if sp > max_byte_addr:
            passed = False
            errors.append(f"  ✗ SP (0x{sp:X}) is out of bounds (max: 0x{max_byte_addr:X})")
        else:
            errors.append(f"  ✓ SP is within valid range")
        
        # Check SP is word-aligned
        if sp % 4 != 0:
            passed = False
            errors.append(f"  ✗ SP (0x{sp:X}) is not word-aligned")
        else:
            errors.append(f"  ✓ SP is word-aligned")
        
        # Print results
        status = "PASS" if passed else "FAIL"
        print(f"\n[{status}] depth_log={depth_log} ({num_words} words, {num_words * 4} bytes)")
        for error in errors:
            print(error)
        
        if not passed:
            all_passed = False
    
    return all_passed

def test_old_vs_new_sp():
    """Compare old hardcoded SP with new calculated SP for depth_log=16."""
    print("\n" + "="*60)
    print("Comparison: Old vs New SP (depth_log=16)")
    print("="*60)
    
    depth_log = 16
    old_sp = 0x40000  # 262,144 bytes (old hardcoded value)
    new_sp = calculate_sp(depth_log)
    
    num_words = 1 << depth_log
    max_byte_addr = (num_words - 1) * 4
    
    print(f"\nCache configuration:")
    print(f"  Words: {num_words} (0x{num_words:X})")
    print(f"  Total capacity: {num_words * 4} bytes (0x{num_words * 4:X})")
    print(f"  Valid address range: 0x00000 to 0x{max_byte_addr:X}")
    
    print(f"\nOld SP (hardcoded):")
    print(f"  Value: 0x{old_sp:X} ({old_sp} bytes)")
    print(f"  Within range: {old_sp <= max_byte_addr} ✗")
    print(f"  Error: {old_sp - max_byte_addr} bytes beyond maximum")
    
    print(f"\nNew SP (calculated):")
    print(f"  Formula: ((1 << {depth_log}) - 1) * 4")
    print(f"  Value: 0x{new_sp:X} ({new_sp} bytes)")
    print(f"  Within range: {new_sp <= max_byte_addr} ✓")
    print(f"  Word-aligned: {new_sp % 4 == 0} ✓")
    
    print(f"\nDifference:")
    print(f"  {old_sp - new_sp} bytes (1 word)")

def test_stack_growth():
    """Test that stack can grow downward from the initial SP."""
    print("\n" + "="*60)
    print("Stack Growth Test (depth_log=16)")
    print("="*60)
    
    depth_log = 16
    sp = calculate_sp(depth_log)
    max_byte_addr = ((1 << depth_log) - 1) * 4
    
    print(f"\nInitial SP: 0x{sp:X}")
    
    # Simulate stack operations from my0to100 program
    stack_operations = [
        ("addi sp, sp, -32", -32),   # First instruction in my0to100
        ("addi sp, sp, -64", -64),   # Deeper function call
        ("addi sp, sp, -128", -128), # Even deeper
    ]
    
    current_sp = sp
    all_valid = True
    
    for description, offset in stack_operations:
        current_sp += offset  # offset is negative
        is_valid = 0 <= current_sp <= max_byte_addr
        status = "✓" if is_valid else "✗"
        print(f"  {status} {description}")
        print(f"     SP = 0x{current_sp:X} ({'valid' if is_valid else 'OUT OF BOUNDS'})")
        if not is_valid:
            all_valid = False
    
    return all_valid

if __name__ == "__main__":
    print("="*60)
    print("Stack Pointer Initialization Test Suite")
    print("="*60)
    
    # Run all tests
    test1_pass = test_sp_initialization()
    test_old_vs_new_sp()
    test2_pass = test_stack_growth()
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"SP Initialization Tests: {'PASS ✓' if test1_pass else 'FAIL ✗'}")
    print(f"Stack Growth Tests: {'PASS ✓' if test2_pass else 'FAIL ✗'}")
    
    if test1_pass and test2_pass:
        print("\n✅ All tests passed!")
        exit(0)
    else:
        print("\n❌ Some tests failed!")
        exit(1)
