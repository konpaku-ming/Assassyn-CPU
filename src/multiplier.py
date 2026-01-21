from assassyn.frontend import *
from .debug_utils import debug_log


def sign_zero_extend(op: Bits, signed: Bits) -> Bits:
    # Helper function to perform sign or zero extension of a 32-bit value to 64 bits.
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
# Carry-Lookahead Adder (CLA) - Hardware Implementation
# =============================================================================
def carry_lookahead_adder_4bit(a: Bits, b: Bits, cin: Bits) -> tuple:
    """
    4-bit Carry-Lookahead Adder (CLA)

    Computes sum and carry-out using generate (G) and propagate (P) signals.
    G[i] = a[i] & b[i]
    P[i] = a[i] ^ b[i]
    C[i+1] = G[i] | (P[i] & C[i])

    Returns (sum, cout) where sum is 4-bit and cout is 1-bit
    """
    # Generate and propagate signals for each bit
    g0 = a[0:0] & b[0:0]
    p0 = a[0:0] ^ b[0:0]
    g1 = a[1:1] & b[1:1]
    p1 = a[1:1] ^ b[1:1]
    g2 = a[2:2] & b[2:2]
    p2 = a[2:2] ^ b[2:2]
    g3 = a[3:3] & b[3:3]
    p3 = a[3:3] ^ b[3:3]

    # Carry lookahead equations
    c0 = cin
    c1 = g0 | (p0 & c0)
    c2 = g1 | (p1 & g0) | (p1 & p0 & c0)
    c3 = g2 | (p2 & g1) | (p2 & p1 & g0) | (p2 & p1 & p0 & c0)
    c4 = g3 | (p3 & g2) | (p3 & p2 & g1) | (p3 & p2 & p1 & g0) | (p3 & p2 & p1 & p0 & c0)

    # Sum computation: S[i] = P[i] ^ C[i]
    s0 = p0 ^ c0
    s1 = p1 ^ c1
    s2 = p2 ^ c2
    s3 = p3 ^ c3

    sum_result = concat(s3, concat(s2, concat(s1, s0)))

    # Group generate and propagate for hierarchical CLA
    group_g = g3 | (p3 & g2) | (p3 & p2 & g1) | (p3 & p2 & p1 & g0)
    group_p = p3 & p2 & p1 & p0

    return (sum_result, c4, group_g, group_p)


def carry_lookahead_adder_16bit(a: Bits, b: Bits, cin: Bits) -> tuple:
    """
    16-bit Carry-Lookahead Adder using four 4-bit CLA blocks

    Returns (sum, cout) where sum is 16-bit and cout is 1-bit
    """
    # First 4-bit block
    s0, c4, g0, p0 = carry_lookahead_adder_4bit(a[0:3], b[0:3], cin)

    # Second 4-bit block
    s1, c8, g1, p1 = carry_lookahead_adder_4bit(a[4:7], b[4:7], c4)

    # Third 4-bit block
    s2, c12, g2, p2 = carry_lookahead_adder_4bit(a[8:11], b[8:11], c8)

    # Fourth 4-bit block
    s3, c16, g3, p3 = carry_lookahead_adder_4bit(a[12:15], b[12:15], c12)

    sum_result = concat(s3, concat(s2, concat(s1, s0)))

    # Group generate and propagate for higher level
    group_g = g3 | (p3 & g2) | (p3 & p2 & g1) | (p3 & p2 & p1 & g0)
    group_p = p3 & p2 & p1 & p0

    return (sum_result, c16, group_g, group_p)


def carry_lookahead_adder_64bit(a: Bits, b: Bits) -> Bits:
    """
    64-bit Carry-Lookahead Adder using four 16-bit CLA blocks

    This is a hierarchical CLA implementation for efficient carry computation.
    """
    cin = Bits(1)(0)

    # First 16-bit block
    s0, c16, g0, p0 = carry_lookahead_adder_16bit(a[0:15], b[0:15], cin)

    # Second 16-bit block
    s1, c32, g1, p1 = carry_lookahead_adder_16bit(a[16:31], b[16:31], c16)

    # Third 16-bit block
    s2, c48, g2, p2 = carry_lookahead_adder_16bit(a[32:47], b[32:47], c32)

    # Fourth 16-bit block
    s3, c64, g3, p3 = carry_lookahead_adder_16bit(a[48:63], b[48:63], c48)

    result = concat(s3, concat(s2, concat(s1, s0)))

    return result


class WallaceTreeMul:
    """
    3-cycle Wallace Tree Multiplier with Carry-Lookahead Adder

    - Cycle 1 (EX_M1): Generate 32 partial products
    - Cycle 2 (EX_M2): Wallace Tree compression Levels 1-8 (32 → 2 rows)
    - Cycle 3 (EX_M3): Final addition using Carry-Lookahead Adder (CLA)
    """

    def __init__(self):
        # Pipeline stage registers
        # Stage 1 (EX_M1): Partial product generation only
        self.m1_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m1_op1 = RegArray(Bits(32), 1, initializer=[0])
        self.m1_op2 = RegArray(Bits(32), 1, initializer=[0])
        self.m1_op1_signed = RegArray(Bits(1), 1, initializer=[0])
        self.m1_op2_signed = RegArray(Bits(1), 1, initializer=[0])
        self.m1_result_high = RegArray(Bits(1), 1, initializer=[0])  # Whether to return high 32 bits
        self.m1_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register

        # Stage 2 (EX_M2): Wallace Tree compression (32 → 2 rows)
        # Store 32 partial products from Stage 1
        self.m2_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m2_result_high = RegArray(Bits(1), 1, initializer=[0])
        self.m2_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register
        # Signed multiplication correction for MULH
        self.m2_signed_correction = RegArray(Bits(32), 1, initializer=[0])
        # 32 partial products from Stage 1
        self.m2_pp0 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp1 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp2 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp3 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp4 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp5 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp6 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp7 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp8 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp9 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp10 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp11 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp12 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp13 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp14 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp15 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp16 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp17 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp18 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp19 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp20 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp21 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp22 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp23 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp24 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp25 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp26 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp27 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp28 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp29 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp30 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_pp31 = RegArray(Bits(64), 1, initializer=[0])

        # Stage 3 (EX_M3): Final addition using Carry-Lookahead Adder
        # After Wallace Tree compression, we have 2 rows that need to be added
        self.m3_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m3_result_high = RegArray(Bits(1), 1, initializer=[0])
        self.m3_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register
        # 2 final rows from Wallace Tree compression output
        self.m3_row0 = RegArray(Bits(64), 1, initializer=[0])
        self.m3_row1 = RegArray(Bits(64), 1, initializer=[0])
        # Signed multiplication correction for MULH
        self.m3_signed_correction = RegArray(Bits(32), 1, initializer=[0])

        # Final result storage
        self.m3_result_ready = RegArray(Bits(1), 1, initializer=[0])
        self.m3_result = RegArray(Bits(32), 1, initializer=[0])

    def is_busy(self):
        # Check if multiplier has operations in flight that require pipeline stall.
        # Returns True when any of stages M1, M2, or M3 are active.
        return self.m1_valid[0] | self.m2_valid[0] | self.m3_valid[0]

    def start_multiply(self, op1, op2, op1_signed, op2_signed, result_high, rd=Bits(5)(0)):
        """
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
        Execute EX_M1 stage: Partial Product Generation only

        This stage generates 32 partial products using AND gates.
        No compression is performed in this cycle.
        """
        # Only process if stage 1 is valid
        with Condition(self.m1_valid[0] == Bits(1)(1)):
            # Read pipeline registers
            op1 = self.m1_op1[0]
            op2 = self.m1_op2[0]
            op1_signed = self.m1_op1_signed[0]
            op2_signed = self.m1_op2_signed[0]

            debug_log("EX_M1: Partial product generation (Cycle 1/3)")
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
            # Step 2: Compute signed multiplication correction for MULH
            # When op2 is signed and negative (op2[31]=1), we need to correct
            # the result because the MSB represents -2^31 instead of +2^31.
            # The correction is: subtract op1 from the high 32 bits of result.
            # =================================================================
            need_correction = op2_signed & op2[31:31]
            signed_correction = need_correction.select(op1, Bits(32)(0))

            # =================================================================
            # Step 3: Generate 32 Partial Products
            # For each bit i of op2: pp[i] = (op2[i] ? op1_ext : 0) << i
            # =================================================================

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

            debug_log("EX_M1: 32 partial products generated")

            # =================================================================
            # Store partial products in stage 2 pipeline registers
            # =================================================================
            self.m2_valid[0] = Bits(1)(1)
            self.m2_result_high[0] = self.m1_result_high[0]
            self.m2_rd[0] = self.m1_rd[0]
            self.m2_signed_correction[0] = signed_correction

            # Store all 32 partial products
            self.m2_pp0[0] = pp0
            self.m2_pp1[0] = pp1
            self.m2_pp2[0] = pp2
            self.m2_pp3[0] = pp3
            self.m2_pp4[0] = pp4
            self.m2_pp5[0] = pp5
            self.m2_pp6[0] = pp6
            self.m2_pp7[0] = pp7
            self.m2_pp8[0] = pp8
            self.m2_pp9[0] = pp9
            self.m2_pp10[0] = pp10
            self.m2_pp11[0] = pp11
            self.m2_pp12[0] = pp12
            self.m2_pp13[0] = pp13
            self.m2_pp14[0] = pp14
            self.m2_pp15[0] = pp15
            self.m2_pp16[0] = pp16
            self.m2_pp17[0] = pp17
            self.m2_pp18[0] = pp18
            self.m2_pp19[0] = pp19
            self.m2_pp20[0] = pp20
            self.m2_pp21[0] = pp21
            self.m2_pp22[0] = pp22
            self.m2_pp23[0] = pp23
            self.m2_pp24[0] = pp24
            self.m2_pp25[0] = pp25
            self.m2_pp26[0] = pp26
            self.m2_pp27[0] = pp27
            self.m2_pp28[0] = pp28
            self.m2_pp29[0] = pp29
            self.m2_pp30[0] = pp30
            self.m2_pp31[0] = pp31

            # Clear stage 1
            self.m1_valid[0] = Bits(1)(0)

    def cycle_m2(self):
        """
        Execute EX_M2 stage: Wallace Tree Compression Levels 1-8 (32 → 2 rows)

        This stage performs all Wallace Tree compression levels, reducing
        32 partial products down to 2 rows.
        """
        # Only process if stage 2 is valid
        with Condition(self.m2_valid[0] == Bits(1)(1)):
            debug_log("EX_M2: Wallace Tree compression (Cycle 2/3)")

            # Read all 32 partial products from pipeline registers
            pp0 = self.m2_pp0[0]
            pp1 = self.m2_pp1[0]
            pp2 = self.m2_pp2[0]
            pp3 = self.m2_pp3[0]
            pp4 = self.m2_pp4[0]
            pp5 = self.m2_pp5[0]
            pp6 = self.m2_pp6[0]
            pp7 = self.m2_pp7[0]
            pp8 = self.m2_pp8[0]
            pp9 = self.m2_pp9[0]
            pp10 = self.m2_pp10[0]
            pp11 = self.m2_pp11[0]
            pp12 = self.m2_pp12[0]
            pp13 = self.m2_pp13[0]
            pp14 = self.m2_pp14[0]
            pp15 = self.m2_pp15[0]
            pp16 = self.m2_pp16[0]
            pp17 = self.m2_pp17[0]
            pp18 = self.m2_pp18[0]
            pp19 = self.m2_pp19[0]
            pp20 = self.m2_pp20[0]
            pp21 = self.m2_pp21[0]
            pp22 = self.m2_pp22[0]
            pp23 = self.m2_pp23[0]
            pp24 = self.m2_pp24[0]
            pp25 = self.m2_pp25[0]
            pp26 = self.m2_pp26[0]
            pp27 = self.m2_pp27[0]
            pp28 = self.m2_pp28[0]
            pp29 = self.m2_pp29[0]
            pp30 = self.m2_pp30[0]
            pp31 = self.m2_pp31[0]

            # =================================================================
            # Wallace Tree Compression Levels 1-8 (32 → 2 rows)
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

            debug_log("EX_M2: Wallace Tree compression complete, 2 rows remaining")

            # =================================================================
            # Store final 2 rows in stage 3 pipeline registers
            # =================================================================
            self.m3_valid[0] = Bits(1)(1)
            self.m3_result_high[0] = self.m2_result_high[0]
            self.m3_rd[0] = self.m2_rd[0]
            self.m3_signed_correction[0] = self.m2_signed_correction[0]

            # Store the 2 final rows
            self.m3_row0[0] = s8_final
            self.m3_row1[0] = c8_final

            # Clear stage 2
            self.m2_valid[0] = Bits(1)(0)

    def cycle_m3(self):
        """
        Execute EX_M3 stage: Final Addition using Carry-Lookahead Adder (CLA)

        This stage completes the multiplication by adding the final 2 rows
        using a carry-lookahead adder.
        """
        # Only process if stage 3 is valid and result is not already ready
        with Condition((self.m3_valid[0] == Bits(1)(1)) & (self.m3_result_ready[0] == Bits(1)(0))):
            debug_log("EX_M3: Final addition using CLA (Cycle 3/3)")

            # Read the 2 final rows from pipeline registers
            s8_final = self.m3_row0[0]
            c8_final = self.m3_row1[0]
            signed_correction = self.m3_signed_correction[0]

            # =================================================================
            # CLA (Carry-Lookahead Adder) - Final Addition
            # =================================================================
            product_64 = carry_lookahead_adder_64bit(s8_final, c8_final)

            # Select which 32 bits to return based on operation type
            partial_low = product_64[0:31].bitcast(Bits(32))
            partial_high_raw = product_64[32:63].bitcast(Bits(32))

            # =================================================================
            # Apply signed multiplication correction for MULH
            # When op2 was signed and negative, we need to subtract op1 from
            # the high 32 bits to correct for treating op2's MSB as positive.
            # =================================================================
            partial_high = (partial_high_raw.bitcast(UInt(32)) - signed_correction.bitcast(UInt(32))).bitcast(Bits(32))

            result = self.m3_result_high[0].select(
                partial_high,  # High 32 bits for MULH/MULHSU/MULHU
                partial_low  # Low 32 bits for MUL
            )

            debug_log("EX_M3: Final result: 0x{:x}", result)

            # Store final result and mark as ready
            self.m3_result[0] = result
            self.m3_result_ready[0] = Bits(1)(1)
            # Clear valid flag since processing is complete
            self.m3_valid[0] = Bits(1)(0)

    def get_result_if_ready(self):
        """
        Get the multiplication result if it's ready (stage 3 complete).
        Returns tuple: (result_valid, result_value, rd)
        """
        return (self.m3_result_ready[0], self.m3_result[0], self.m3_rd[0])

    def clear_result(self):
        """Clear the result after it has been consumed"""
        self.m3_result_ready[0] = Bits(1)(0)