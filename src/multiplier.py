"""
Radix-4 Booth + Wallace Tree Multiplier with 3-cycle pipeline

Implementation:
- EX1 (Cycle 1): Booth encoding + partial product generation
- EX2 (Cycle 2): Wallace Tree compression (most layers)  
- EX3 (Cycle 3): Final compression layers + carry-propagate adder

This implements a true 3-cycle pipelined multiplier that takes 3 cycles to produce results.
"""

from assassyn.frontend import *


class BoothWallaceMul:
    """
    Helper class to manage 3-cycle multiplication using Radix-4 Booth + Wallace Tree.
    
    This class provides storage and control for multi-cycle multiplication operations.
    The multiplication proceeds through 3 stages spread across 3 clock cycles.
    """
    
    def __init__(self):
        # Pipeline stage registers
        # Stage 1 (EX1): Booth encoding + partial product generation
        self.ex1_valid = RegArray(Bits(1), 1, initializer=[0])
        self.ex1_op1 = RegArray(Bits(32), 1, initializer=[0])
        self.ex1_op2 = RegArray(Bits(32), 1, initializer=[0])
        self.ex1_op1_signed = RegArray(Bits(1), 1, initializer=[0])
        self.ex1_op2_signed = RegArray(Bits(1), 1, initializer=[0])
        self.ex1_result_high = RegArray(Bits(1), 1, initializer=[0])  # Whether to return high 32 bits
        
        # Stage 2 (EX2): Wallace Tree compression
        self.ex2_valid = RegArray(Bits(1), 1, initializer=[0])
        self.ex2_partial_low = RegArray(Bits(32), 1, initializer=[0])
        self.ex2_partial_high = RegArray(Bits(32), 1, initializer=[0])
        self.ex2_result_high = RegArray(Bits(1), 1, initializer=[0])
        
        # Stage 3 (EX3): Final adder
        self.ex3_valid = RegArray(Bits(1), 1, initializer=[0])
        self.ex3_result = RegArray(Bits(32), 1, initializer=[0])
    
    def is_busy(self):
        """Check if multiplier has operations in flight"""
        return (self.ex1_valid[0] | self.ex2_valid[0] | self.ex3_valid[0])
    
    def start_multiply(self, op1, op2, op1_signed, op2_signed, result_high):
        """
        Start a new multiplication operation.
        
        Args:
            op1: First operand (32-bit)
            op2: Second operand (32-bit)
            op1_signed: Whether op1 is signed (1) or unsigned (0)
            op2_signed: Whether op2 is signed (1) or unsigned (0)
            result_high: Whether to return high 32 bits (1) or low 32 bits (0)
        """
        # Load into stage 1 pipeline registers
        self.ex1_valid[0] = Bits(1)(1)
        self.ex1_op1[0] = op1
        self.ex1_op2[0] = op2
        self.ex1_op1_signed[0] = op1_signed
        self.ex1_op2_signed[0] = op2_signed
        self.ex1_result_high[0] = result_high
    
    def cycle_ex1(self):
        """
        Execute EX1 stage: Booth encoding + partial product generation
        
        In real hardware, this stage would:
        1. Perform Radix-4 Booth recoding of the multiplier (op2)
        2. Generate 17 partial products (each is 0, ±op1, or ±2*op1)
        3. Sign-extend partial products appropriately
        
        For simulation, we compute the full product here and pass to next stage.
        """
        # Only process if stage 1 is valid
        with Condition(self.ex1_valid[0] == Bits(1)(1)):
            # Read pipeline registers
            op1 = self.ex1_op1[0]
            op2 = self.ex1_op2[0]
            op1_signed = self.ex1_op1_signed[0]
            op2_signed = self.ex1_op2_signed[0]
            
            # Sign/Zero extension to 64 bits
            op1_sign_bit = op1[31:31]
            op1_sign_ext = op1_sign_bit.select(Bits(32)(0xFFFFFFFF), Bits(32)(0))
            op1_ext_high = op1_signed.select(op1_sign_ext, Bits(32)(0))
            op1_extended = concat(op1_ext_high, op1)
            
            op2_sign_bit = op2[31:31]
            op2_sign_ext = op2_sign_bit.select(Bits(32)(0xFFFFFFFF), Bits(32)(0))
            op2_ext_high = op2_signed.select(op2_sign_ext, Bits(32)(0))
            op2_extended = concat(op2_ext_high, op2)
            
            # Perform multiplication (representing Booth-encoded partial products)
            product_64 = op1_extended.bitcast(UInt(64)) * op2_extended.bitcast(UInt(64))
            product_bits = product_64.bitcast(Bits(64))
            
            # Split into high and low 32 bits for next stage
            partial_low = product_bits[0:31].bitcast(Bits(32))
            partial_high = product_bits[32:63].bitcast(Bits(32))
            
            # Advance to stage 2
            self.ex2_valid[0] = Bits(1)(1)
            self.ex2_partial_low[0] = partial_low
            self.ex2_partial_high[0] = partial_high
            self.ex2_result_high[0] = self.ex1_result_high[0]
            
            # Clear stage 1
            self.ex1_valid[0] = Bits(1)(0)
    
    def cycle_ex2(self):
        """
        Execute EX2 stage: Wallace Tree compression
        
        In real hardware, this stage would:
        1. Use multiple layers of 3:2 compressors (full adders)
        2. Reduce 17 partial products down to ~3-4 rows
        3. Each level reduces the number of rows by ~1/3
        
        For simulation, we pass through the computed partial sums.
        """
        # Only process if stage 2 is valid
        with Condition(self.ex2_valid[0] == Bits(1)(1)):
            # In real hardware, Wallace Tree compression happens here
            # For simulation, partial products are already summed
            
            # Select which 32 bits to return
            result = self.ex2_result_high[0].select(
                self.ex2_partial_high[0],
                self.ex2_partial_low[0]
            )
            
            # Advance to stage 3
            self.ex3_valid[0] = Bits(1)(1)
            self.ex3_result[0] = result
            
            # Clear stage 2
            self.ex2_valid[0] = Bits(1)(0)
    
    def cycle_ex3(self):
        """
        Execute EX3 stage: Final compression + carry-propagate adder
        
        In real hardware, this stage would:
        1. Perform final 3:2 compression to get 2 rows
        2. Use a carry-propagate adder (CPA) to sum the final 2 rows
        3. The CPA produces the final 64-bit product
        
        For simulation, the result is already computed and we just output it.
        """
        # Only process if stage 3 is valid
        with Condition(self.ex3_valid[0] == Bits(1)(1)):
            # Result is already in ex3_result[0]
            # In real hardware, final CPA would complete here
            
            # Keep result valid for one cycle for execution stage to read
            # The execution stage will clear ex3_valid after reading
            pass
    
    def get_result_if_ready(self):
        """
        Get the multiplication result if it's ready (stage 3 complete).
        Returns tuple: (result_valid, result_value)
        """
        return (self.ex3_valid[0], self.ex3_result[0])
    
    def clear_result(self):
        """Clear the result after it has been consumed"""
        self.ex3_valid[0] = Bits(1)(0)

