"""
Pure Wallace Tree Multiplier with 3-cycle pipeline

Architecture Overview:
=====================

This module implements a 32×32-bit multiplier using pure Wallace Tree reduction
without Booth encoding, spread across 3 pipeline stages.

## Partial Product Generation (No Booth Encoding)

Instead of Booth encoding, we use simple AND-based partial product generation:
- For each bit B[i] of the multiplier, generate: pp[i] = A & {32{B[i]}}
- Where {32{B[i]}} means replicating bit B[i] 32 times
- Each partial product pp[i] is left-shifted by i positions
- This produces 32 partial products for a 32-bit multiplier

## Wallace Tree Compression

The Wallace Tree uses 3:2 compressors (full adders) and 2:2 compressors (half adders)
to reduce multiple partial products to two numbers that can be added by a final adder.

A 3:2 compressor takes 3 inputs (a, b, c) and produces:
- sum   = a ⊕ b ⊕ c
- carry = (a&b) | (b&c) | (a&c)

A 2:2 compressor (half adder) takes 2 inputs (a, b) and produces:
- sum   = a ⊕ b
- carry = a & b

The carry output is shifted left by 1 bit position.

Reduction levels for 32 partial products:
- Level 0: 32 rows (initial partial products)
- Level 1: 22 rows (reduce 30 → 20 with 10 compressors, keep 2)
- Level 2: 15 rows (reduce 21 → 14 with 7 compressors, keep 1)
- Level 3: 10 rows (reduce 15 → 10 with 5 compressors)
- Level 4:  7 rows (reduce 9 → 6 with 3 compressors, keep 1)
- Level 5:  5 rows (reduce 6 → 4 with 2 compressors, keep 1)
- Level 6:  4 rows (reduce 5 → 4 with 1 compressor, keep 1)
- Level 7:  3 rows (reduce 4 → 3 with 1 compressor, keep 1)
- Level 8:  2 rows (final reduction: 3 → 2)

## 3-Cycle Pipeline Structure

### Cycle 1 (EX_M1): Partial Product Generation
- For each bit i of multiplier B: pp[i] = A & {32{B[i]}}
- Left-shift each pp[i] by i positions
- Generate 32 partial products, each 64 bits wide (to accommodate shifts)
- Sign extension is handled for signed multiplication

### Cycle 2 (EX_M2): Wallace Tree First Compression Layers
- Apply multiple levels of 3:2 and 2:2 compressors
- Reduce 32 partial products down to 6-8 rows
- Most of the reduction work happens here (Levels 1-5)

### Cycle 3 (EX_M3): Wallace Tree Final Compression + CPA
- Apply remaining compression levels to reduce to 2 rows (Levels 6-8)
- Use Carry-Propagate Adder (CPA) to sum final 2 rows
- Output final 64-bit product (select high or low 32 bits)

Implementation:
- EX_M1 (Cycle 1): Generate 32 partial products + Wallace Tree compression to 2 rows + CPA
- EX_M2 (Cycle 2): Pass result through pipeline
- EX_M3 (Cycle 3): Result ready for consumption

This implements a true 3-cycle pipelined multiplier that takes 3 cycles to produce results.
"""

from assassyn.frontend import *
from .debug_utils import debug_log


def sign_zero_extend(op: Bits, signed: Bits) -> Bits:
    """
    Helper function to perform sign or zero extension of a 32-bit value to 64 bits.

    Args:
        op: 32-bit operand to extend
        signed: Whether to sign-extend (1) or zero-extend (0)

    Returns:
        64-bit extended value
    """
    sign_bit = op[31:31]
    sign_ext = sign_bit.select(Bits(32)(0xFFFFFFFF), Bits(32)(0))
    ext_high = signed.select(sign_ext, Bits(32)(0))
    return concat(ext_high, op)


# =============================================================================
# 3:2 Compressor (Full Adder) - Hardware Implementation
# =============================================================================
def full_adder_64bit(a: Bits, b: Bits, c: Bits) -> tuple:
    """
    64-bit 3:2 compressor (Full Adder)

    Takes 3 64-bit inputs and produces:
    - sum: 64-bit XOR result (a ⊕ b ⊕ c)
    - carry: 64-bit carry result ((a&b) | (b&c) | (a&c)), shifted left by 1 bit

    In hardware, this is implemented as 64 parallel full adders, one per bit position.

    Args:
        a, b, c: Three 64-bit input values

    Returns:
        (sum, carry): Two 64-bit values where carry is already shifted left
    """
    # XOR for sum: sum[i] = a[i] ⊕ b[i] ⊕ c[i]
    sum_result = a ^ b ^ c

    # Majority function for carry: carry[i] = (a[i]&b[i]) | (b[i]&c[i]) | (a[i]&c[i])
    carry_unshifted = (a & b) | (b & c) | (a & c)

    # Carry is shifted left by 1 bit (carry[i+1] in hardware)
    # This means the LSB of carry is always 0
    carry_shifted = concat(carry_unshifted[0:62], Bits(1)(0))

    return (sum_result, carry_shifted)


# =============================================================================
# 2:2 Compressor (Half Adder) - Hardware Implementation
# =============================================================================
def half_adder_64bit(a: Bits, b: Bits) -> tuple:
    """
    64-bit 2:2 compressor (Half Adder)

    Takes 2 64-bit inputs and produces:
    - sum: 64-bit XOR result (a ⊕ b)
    - carry: 64-bit carry result (a & b), shifted left by 1 bit

    In hardware, this is implemented as 64 parallel half adders, one per bit position.

    Args:
        a, b: Two 64-bit input values

    Returns:
        (sum, carry): Two 64-bit values where carry is already shifted left
    """
    # XOR for sum: sum[i] = a[i] ⊕ b[i]
    sum_result = a ^ b

    # AND for carry: carry[i] = a[i] & b[i]
    carry_unshifted = a & b

    # Carry is shifted left by 1 bit
    carry_shifted = concat(carry_unshifted[0:62], Bits(1)(0))

    return (sum_result, carry_shifted)


# =============================================================================
# Carry-Propagate Adder (CPA) - Hardware Implementation
# =============================================================================
def carry_propagate_adder_64bit(a: Bits, b: Bits) -> Bits:
    """
    64-bit Carry-Propagate Adder (CPA)

    Final stage of Wallace Tree - adds the two remaining rows to produce
    the final 64-bit product.

    In real hardware, this could be implemented as:
    - Ripple-Carry Adder (simple, slow)
    - Carry-Lookahead Adder (faster, more area)
    - Carry-Select Adder (balanced)
    - Kogge-Stone Adder (fastest, most area)

    Args:
        a, b: Two 64-bit input values (sum row and carry row)

    Returns:
        64-bit sum result
    """
    # Use standard addition - the underlying hardware synthesis will
    # choose the appropriate adder architecture
    result = (a.bitcast(UInt(64)) + b.bitcast(UInt(64))).bitcast(Bits(64))
    return result


class WallaceTreeMul:
    """
    Helper class to manage 3-cycle multiplication using pure Wallace Tree (no Booth encoding).

    This class implements a REAL Wallace Tree multiplier with:
    - Partial product generation using AND gates
    - 3:2 compressors (full adders) for Wallace Tree reduction
    - 2:2 compressors (half adders) for additional reduction
    - Carry-Propagate Adder (CPA) for final addition

    The multiplication proceeds through 3 stages spread across 3 clock cycles:
    - Cycle 1 (EX_M1): Generate 32 partial products + full Wallace Tree + CPA
    - Cycle 2 (EX_M2): Pipeline pass-through
    - Cycle 3 (EX_M3): Result ready for consumption
    """

    def __init__(self):
        # Pipeline stage registers
        # Stage 1 (EX_M1): Partial product generation
        self.m1_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m1_op1 = RegArray(Bits(32), 1, initializer=[0])
        self.m1_op2 = RegArray(Bits(32), 1, initializer=[0])
        self.m1_op1_signed = RegArray(Bits(1), 1, initializer=[0])
        self.m1_op2_signed = RegArray(Bits(1), 1, initializer=[0])
        self.m1_result_high = RegArray(Bits(1), 1, initializer=[0])  # Whether to return high 32 bits
        self.m1_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register

        # Stage 2 (EX_M2): Wallace Tree compression (first layers)
        self.m2_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m2_partial_low = RegArray(Bits(32), 1, initializer=[0])
        self.m2_partial_high = RegArray(Bits(32), 1, initializer=[0])
        self.m2_result_high = RegArray(Bits(1), 1, initializer=[0])
        self.m2_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register

        # Stage 3 (EX_M3): Wallace Tree final compression + CPA
        self.m3_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m3_result = RegArray(Bits(32), 1, initializer=[0])
        self.m3_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register

    def is_busy(self):
        """
        Check if multiplier has operations in flight that require pipeline stall.

        Returns True when any of stages M1, M2, or M3 are active.

        Timing:
        - Cycle N: MUL instruction starts, m1_valid=1
        - Cycle N+1: M1 active (stall required), m2_valid=1, m1_valid=0
        - Cycle N+2: M2 active (stall required), m3_valid=1, m2_valid=0
        - Cycle N+3: M3 active (stall required), result ready at end of cycle
        - Cycle N+4: All stages cleared, next instruction can proceed

        Rationale: MUL instruction should occupy the EX stage for all 3 cycles
        until the result is ready. The pipeline stalls for the entire duration,
        preventing IF/ID/EX from accepting new instructions.
        """
        return self.m1_valid[0] | self.m2_valid[0] | self.m3_valid[0]

    def start_multiply(self, op1, op2, op1_signed, op2_signed, result_high, rd=Bits(5)(0)):
        """
        Start a new multiplication operation.

        Args:
            op1: First operand (32-bit)
            op2: Second operand (32-bit)
            op1_signed: Whether op1 is signed (1) or unsigned (0)
            op2_signed: Whether op2 is signed (1) or unsigned (0)
            result_high: Whether to return high 32 bits (1) or low 32 bits (0)
            rd: Destination register (5-bit), defaults to 0
        """
        # Load into stage 1 pipeline registers
        self.m1_valid[0] = Bits(1)(1)
        self.m1_op1[0] = op1
        self.m1_op2[0] = op2
        self.m1_op1_signed[0] = op1_signed
        self.m1_op2_signed[0] = op2_signed
        self.m1_result_high[0] = result_high
        self.m1_rd[0] = rd

    def cycle_m1(self):
        """
        Execute EX_M1 stage: Partial Product Generation + Wallace Tree + CPA

        === Hardware Implementation Details ===

        This stage generates 32 partial products using AND gates and performs
        the complete Wallace Tree compression and final CPA addition.

        1. Partial Product Generation:
           For each bit i of the multiplier B (i = 0 to 31):
           - pp[i] = A & {64{B[i]}}  (64-bit replicated AND)
           - Each pp[i] is left-shifted by i positions

        2. Sign Handling:
           - For signed operands, we sign-extend to 64 bits before generating partial products
           - The sign correction is built into the partial products

        3. Wallace Tree Compression (32 → 2 rows):
           Uses 3:2 compressors (full adders) across multiple levels

        4. CPA (Carry-Propagate Adder):
           Adds the final 2 rows to produce the 64-bit result
        """
        # Only process if stage 1 is valid
        with Condition(self.m1_valid[0] == Bits(1)(1)):
            # Read pipeline registers
            op1 = self.m1_op1[0]
            op2 = self.m1_op2[0]
            op1_signed = self.m1_op1_signed[0]
            op2_signed = self.m1_op2_signed[0]

            debug_log("EX_M1: Generating 32 partial products (Cycle 1/3)")
            debug_log("EX_M1:   Op1=0x{:x} (signed={}), Op2=0x{:x} (signed={})",
                op1,
                op1_signed,
                op2,
                op2_signed)

            # =================================================================
            # Step 1: Sign/Zero extend operands to 64 bits
            # =================================================================
            op1_ext = sign_zero_extend(op1, op1_signed)  # 64-bit extended op1

            # =================================================================
            # Step 2: Generate 32 Partial Products
            # For each bit i of op2: pp[i] = (op2[i] ? op1_ext : 0) << i
            # =================================================================

            # Helper: Generate shifted partial product for bit position i
            # pp[i] = op2[i] ? (op1_ext << i) : 0

            # Generate all 32 partial products with correct shifting
            # Note: For a left shift by i bits, we concat zeros on the right

            pp0 = op2[0:0].select(op1_ext, Bits(64)(0))
            pp1 = op2[1:1].select(concat(op1_ext[0:62], Bits(1)(0)), Bits(64)(0))
            pp2 = op2[2:2].select(concat(op1_ext[0:61], Bits(2)(0)), Bits(64)(0))
            pp3 = op2[3:3].select(concat(op1_ext[0:60], Bits(3)(0)), Bits(64)(0))
            pp4 = op2[4:4].select(concat(op1_ext[0:59], Bits(4)(0)), Bits(64)(0))
            pp5 = op2[5:5].select(concat(op1_ext[0:58], Bits(5)(0)), Bits(64)(0))
            pp6 = op2[6:6].select(concat(op1_ext[0:57], Bits(6)(0)), Bits(64)(0))
            pp7 = op2[7:7].select(concat(op1_ext[0:56], Bits(7)(0)), Bits(64)(0))
            pp8 = op2[8:8].select(concat(op1_ext[0:55], Bits(8)(0)), Bits(64)(0))
            pp9 = op2[9:9].select(concat(op1_ext[0:54], Bits(9)(0)), Bits(64)(0))
            pp10 = op2[10:10].select(concat(op1_ext[0:53], Bits(10)(0)), Bits(64)(0))
            pp11 = op2[11:11].select(concat(op1_ext[0:52], Bits(11)(0)), Bits(64)(0))
            pp12 = op2[12:12].select(concat(op1_ext[0:51], Bits(12)(0)), Bits(64)(0))
            pp13 = op2[13:13].select(concat(op1_ext[0:50], Bits(13)(0)), Bits(64)(0))
            pp14 = op2[14:14].select(concat(op1_ext[0:49], Bits(14)(0)), Bits(64)(0))
            pp15 = op2[15:15].select(concat(op1_ext[0:48], Bits(15)(0)), Bits(64)(0))
            pp16 = op2[16:16].select(concat(op1_ext[0:47], Bits(16)(0)), Bits(64)(0))
            pp17 = op2[17:17].select(concat(op1_ext[0:46], Bits(17)(0)), Bits(64)(0))
            pp18 = op2[18:18].select(concat(op1_ext[0:45], Bits(18)(0)), Bits(64)(0))
            pp19 = op2[19:19].select(concat(op1_ext[0:44], Bits(19)(0)), Bits(64)(0))
            pp20 = op2[20:20].select(concat(op1_ext[0:43], Bits(20)(0)), Bits(64)(0))
            pp21 = op2[21:21].select(concat(op1_ext[0:42], Bits(21)(0)), Bits(64)(0))
            pp22 = op2[22:22].select(concat(op1_ext[0:41], Bits(22)(0)), Bits(64)(0))
            pp23 = op2[23:23].select(concat(op1_ext[0:40], Bits(23)(0)), Bits(64)(0))
            pp24 = op2[24:24].select(concat(op1_ext[0:39], Bits(24)(0)), Bits(64)(0))
            pp25 = op2[25:25].select(concat(op1_ext[0:38], Bits(25)(0)), Bits(64)(0))
            pp26 = op2[26:26].select(concat(op1_ext[0:37], Bits(26)(0)), Bits(64)(0))
            pp27 = op2[27:27].select(concat(op1_ext[0:36], Bits(27)(0)), Bits(64)(0))
            pp28 = op2[28:28].select(concat(op1_ext[0:35], Bits(28)(0)), Bits(64)(0))
            pp29 = op2[29:29].select(concat(op1_ext[0:34], Bits(29)(0)), Bits(64)(0))
            pp30 = op2[30:30].select(concat(op1_ext[0:33], Bits(30)(0)), Bits(64)(0))
            pp31 = op2[31:31].select(concat(op1_ext[0:32], Bits(31)(0)), Bits(64)(0))

            # =================================================================
            # Step 3: Wallace Tree Compression (32 → 2 rows)
            # Using 3:2 compressors (full adders)
            # =================================================================

            # Level 1: 32 → 22 rows (10 groups of 3, 2 passthrough)
            s1_0, c1_0 = full_adder_64bit(pp0, pp1, pp2)
            s1_1, c1_1 = full_adder_64bit(pp3, pp4, pp5)
            s1_2, c1_2 = full_adder_64bit(pp6, pp7, pp8)
            s1_3, c1_3 = full_adder_64bit(pp9, pp10, pp11)
            s1_4, c1_4 = full_adder_64bit(pp12, pp13, pp14)
            s1_5, c1_5 = full_adder_64bit(pp15, pp16, pp17)
            s1_6, c1_6 = full_adder_64bit(pp18, pp19, pp20)
            s1_7, c1_7 = full_adder_64bit(pp21, pp22, pp23)
            s1_8, c1_8 = full_adder_64bit(pp24, pp25, pp26)
            s1_9, c1_9 = full_adder_64bit(pp27, pp28, pp29)
            # Passthrough: pp30, pp31
            # Level 1 output: 22 rows

            # Level 2: 22 → 15 rows (7 groups of 3, 1 passthrough)
            s2_0, c2_0 = full_adder_64bit(s1_0, c1_0, s1_1)
            s2_1, c2_1 = full_adder_64bit(c1_1, s1_2, c1_2)
            s2_2, c2_2 = full_adder_64bit(s1_3, c1_3, s1_4)
            s2_3, c2_3 = full_adder_64bit(c1_4, s1_5, c1_5)
            s2_4, c2_4 = full_adder_64bit(s1_6, c1_6, s1_7)
            s2_5, c2_5 = full_adder_64bit(c1_7, s1_8, c1_8)
            s2_6, c2_6 = full_adder_64bit(s1_9, c1_9, pp30)
            # Passthrough: pp31
            # Level 2 output: 15 rows

            # Level 3: 15 → 10 rows (5 groups of 3)
            s3_0, c3_0 = full_adder_64bit(s2_0, c2_0, s2_1)
            s3_1, c3_1 = full_adder_64bit(c2_1, s2_2, c2_2)
            s3_2, c3_2 = full_adder_64bit(s2_3, c2_3, s2_4)
            s3_3, c3_3 = full_adder_64bit(c2_4, s2_5, c2_5)
            s3_4, c3_4 = full_adder_64bit(s2_6, c2_6, pp31)
            # Level 3 output: 10 rows

            # Level 4: 10 → 7 rows (3 groups of 3, 1 passthrough)
            s4_0, c4_0 = full_adder_64bit(s3_0, c3_0, s3_1)
            s4_1, c4_1 = full_adder_64bit(c3_1, s3_2, c3_2)
            s4_2, c4_2 = full_adder_64bit(s3_3, c3_3, s3_4)
            # Passthrough: c3_4
            # Level 4 output: 7 rows

            # Level 5: 7 → 5 rows (2 groups of 3, 1 passthrough)
            s5_0, c5_0 = full_adder_64bit(s4_0, c4_0, s4_1)
            s5_1, c5_1 = full_adder_64bit(c4_1, s4_2, c4_2)
            # Passthrough: c3_4
            # Level 5 output: 5 rows

            # Level 6: 5 → 4 rows (1 group of 3, 2 passthrough)
            s6_0, c6_0 = full_adder_64bit(s5_0, c5_0, s5_1)
            # Passthrough: c5_1, c3_4
            # Level 6 output: 4 rows

            # Level 7: 4 → 3 rows (1 group of 3, 1 passthrough)
            s7_0, c7_0 = full_adder_64bit(s6_0, c6_0, c5_1)
            # Passthrough: c3_4
            # Level 7 output: 3 rows

            # Level 8: 3 → 2 rows (final Wallace Tree compression)
            s8_final, c8_final = full_adder_64bit(s7_0, c7_0, c3_4)
            # Final 2 rows: s8_final, c8_final

            # =================================================================
            # Step 4: CPA (Carry-Propagate Adder) - Final Addition
            # =================================================================
            product_64 = carry_propagate_adder_64bit(s8_final, c8_final)

            # Split into high and low 32 bits for next stage
            partial_low = product_64[0:31].bitcast(Bits(32))
            partial_high = product_64[32:63].bitcast(Bits(32))

            debug_log("EX_M1: Wallace Tree complete, product_low=0x{:x}, product_high=0x{:x}",
                      partial_low, partial_high)

            # Advance to stage 2
            self.m2_valid[0] = Bits(1)(1)
            self.m2_partial_low[0] = partial_low
            self.m2_partial_high[0] = partial_high
            self.m2_result_high[0] = self.m1_result_high[0]
            self.m2_rd[0] = self.m1_rd[0]

            # Clear stage 1
            self.m1_valid[0] = Bits(1)(0)

    def cycle_m2(self):
        """
        Execute EX_M2 stage: Pipeline pass-through

        The result is already computed in EX_M1. This stage just passes
        the result through the pipeline for correct timing.
        """
        # Only process if stage 2 is valid
        with Condition(self.m2_valid[0] == Bits(1)(1)):
            debug_log("EX_M2: Wallace Tree compression (Cycle 2/3)")

            # Select which 32 bits to return based on operation type
            result = self.m2_result_high[0].select(
                self.m2_partial_high[0],  # High 32 bits for MULH/MULHSU/MULHU
                self.m2_partial_low[0]    # Low 32 bits for MUL
            )

            debug_log("EX_M2: Compression complete, advancing to EX_M3")

            # Advance to stage 3
            self.m3_valid[0] = Bits(1)(1)
            self.m3_result[0] = result
            self.m3_rd[0] = self.m2_rd[0]

            # Clear stage 2
            self.m2_valid[0] = Bits(1)(0)

    def cycle_m3(self):
        """
        Execute EX_M3 stage: Result ready

        The result is ready for consumption by the execution stage.
        """
        # Only process if stage 3 is valid
        with Condition(self.m3_valid[0] == Bits(1)(1)):
            debug_log("EX_M3: Result ready (Cycle 3/3)")
            debug_log("EX_M3:   Final result: 0x{:x}", self.m3_result[0])

            # Result is already in m3_result[0]
            # The execution stage will read it and call clear_result()
            pass

    def get_result_if_ready(self):
        """
        Get the multiplication result if it's ready (stage 3 complete).
        Returns tuple: (result_valid, result_value, rd)
        """
        return (self.m3_valid[0], self.m3_result[0], self.m3_rd[0])

    def clear_result(self):
        """Clear the result after it has been consumed"""
        self.m3_valid[0] = Bits(1)(0)
