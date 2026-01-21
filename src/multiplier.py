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
    16-bit Carry-Lookahead Adder using four 4-bit CLA blocks with true parallel carry lookahead.

    Uses a second-level LCU to compute carries c4, c8, c12 in parallel from cin.
    Returns (sum, cout, group_g, group_p) where sum is 16-bit and cout is 1-bit.
    """
    # Get results from each 4-bit block with dummy cin to extract g and p
    # Note: g and p don't depend on cin, only the sum and cout do
    # But we need the sum, so we compute everything in one pass per block
    # using the computed parallel carries

    # First, extract g and p from each block (they don't depend on cin)
    # We compute the 4-bit blocks' internal g/p directly
    # For block 0: bits 0-3
    g0_0 = a[0:0] & b[0:0]
    p0_0 = a[0:0] ^ b[0:0]
    g0_1 = a[1:1] & b[1:1]
    p0_1 = a[1:1] ^ b[1:1]
    g0_2 = a[2:2] & b[2:2]
    p0_2 = a[2:2] ^ b[2:2]
    g0_3 = a[3:3] & b[3:3]
    p0_3 = a[3:3] ^ b[3:3]
    g0 = g0_3 | (p0_3 & g0_2) | (p0_3 & p0_2 & g0_1) | (p0_3 & p0_2 & p0_1 & g0_0)
    p0 = p0_3 & p0_2 & p0_1 & p0_0

    # For block 1: bits 4-7
    g1_0 = a[4:4] & b[4:4]
    p1_0 = a[4:4] ^ b[4:4]
    g1_1 = a[5:5] & b[5:5]
    p1_1 = a[5:5] ^ b[5:5]
    g1_2 = a[6:6] & b[6:6]
    p1_2 = a[6:6] ^ b[6:6]
    g1_3 = a[7:7] & b[7:7]
    p1_3 = a[7:7] ^ b[7:7]
    g1 = g1_3 | (p1_3 & g1_2) | (p1_3 & p1_2 & g1_1) | (p1_3 & p1_2 & p1_1 & g1_0)
    p1 = p1_3 & p1_2 & p1_1 & p1_0

    # For block 2: bits 8-11
    g2_0 = a[8:8] & b[8:8]
    p2_0 = a[8:8] ^ b[8:8]
    g2_1 = a[9:9] & b[9:9]
    p2_1 = a[9:9] ^ b[9:9]
    g2_2 = a[10:10] & b[10:10]
    p2_2 = a[10:10] ^ b[10:10]
    g2_3 = a[11:11] & b[11:11]
    p2_3 = a[11:11] ^ b[11:11]
    g2 = g2_3 | (p2_3 & g2_2) | (p2_3 & p2_2 & g2_1) | (p2_3 & p2_2 & p2_1 & g2_0)
    p2 = p2_3 & p2_2 & p2_1 & p2_0

    # For block 3: bits 12-15
    g3_0 = a[12:12] & b[12:12]
    p3_0 = a[12:12] ^ b[12:12]
    g3_1 = a[13:13] & b[13:13]
    p3_1 = a[13:13] ^ b[13:13]
    g3_2 = a[14:14] & b[14:14]
    p3_2 = a[14:14] ^ b[14:14]
    g3_3 = a[15:15] & b[15:15]
    p3_3 = a[15:15] ^ b[15:15]
    g3 = g3_3 | (p3_3 & g3_2) | (p3_3 & p3_2 & g3_1) | (p3_3 & p3_2 & p3_1 & g3_0)
    p3 = p3_3 & p3_2 & p3_1 & p3_0

    # Second-level Lookahead Carry Unit (LCU): compute all carries in parallel
    c4 = g0 | (p0 & cin)
    c8 = g1 | (p1 & g0) | (p1 & p0 & cin)
    c12 = g2 | (p2 & g1) | (p2 & p1 & g0) | (p2 & p1 & p0 & cin)
    c16 = g3 | (p3 & g2) | (p3 & p2 & g1) | (p3 & p2 & p1 & g0) | (p3 & p2 & p1 & p0 & cin)

    # Now compute sums using the computed carries and cached p values
    # Block 0 sums (using cin)
    c0_0 = cin
    c0_1 = g0_0 | (p0_0 & c0_0)
    c0_2 = g0_1 | (p0_1 & g0_0) | (p0_1 & p0_0 & c0_0)
    c0_3 = g0_2 | (p0_2 & g0_1) | (p0_2 & p0_1 & g0_0) | (p0_2 & p0_1 & p0_0 & c0_0)
    s0_0 = p0_0 ^ c0_0
    s0_1 = p0_1 ^ c0_1
    s0_2 = p0_2 ^ c0_2
    s0_3 = p0_3 ^ c0_3
    s0 = concat(s0_3, concat(s0_2, concat(s0_1, s0_0)))

    # Block 1 sums (using c4)
    c1_0 = c4
    c1_1 = g1_0 | (p1_0 & c1_0)
    c1_2 = g1_1 | (p1_1 & g1_0) | (p1_1 & p1_0 & c1_0)
    c1_3 = g1_2 | (p1_2 & g1_1) | (p1_2 & p1_1 & g1_0) | (p1_2 & p1_1 & p1_0 & c1_0)
    s1_0 = p1_0 ^ c1_0
    s1_1 = p1_1 ^ c1_1
    s1_2 = p1_2 ^ c1_2
    s1_3 = p1_3 ^ c1_3
    s1 = concat(s1_3, concat(s1_2, concat(s1_1, s1_0)))

    # Block 2 sums (using c8)
    c2_0 = c8
    c2_1 = g2_0 | (p2_0 & c2_0)
    c2_2 = g2_1 | (p2_1 & g2_0) | (p2_1 & p2_0 & c2_0)
    c2_3 = g2_2 | (p2_2 & g2_1) | (p2_2 & p2_1 & g2_0) | (p2_2 & p2_1 & p2_0 & c2_0)
    s2_0 = p2_0 ^ c2_0
    s2_1 = p2_1 ^ c2_1
    s2_2 = p2_2 ^ c2_2
    s2_3 = p2_3 ^ c2_3
    s2 = concat(s2_3, concat(s2_2, concat(s2_1, s2_0)))

    # Block 3 sums (using c12)
    c3_0 = c12
    c3_1 = g3_0 | (p3_0 & c3_0)
    c3_2 = g3_1 | (p3_1 & g3_0) | (p3_1 & p3_0 & c3_0)
    c3_3 = g3_2 | (p3_2 & g3_1) | (p3_2 & p3_1 & g3_0) | (p3_2 & p3_1 & p3_0 & c3_0)
    s3_0 = p3_0 ^ c3_0
    s3_1 = p3_1 ^ c3_1
    s3_2 = p3_2 ^ c3_2
    s3_3 = p3_3 ^ c3_3
    s3 = concat(s3_3, concat(s3_2, concat(s3_1, s3_0)))

    sum_result = concat(s3, concat(s2, concat(s1, s0)))

    # Group generate and propagate for higher level
    group_g = g3 | (p3 & g2) | (p3 & p2 & g1) | (p3 & p2 & p1 & g0)
    group_p = p3 & p2 & p1 & p0

    return (sum_result, c16, group_g, group_p)


def carry_lookahead_adder_64bit(a: Bits, b: Bits) -> Bits:
    """
    64-bit Carry-Lookahead Adder using four 16-bit CLA blocks with true parallel carry lookahead.

    This is a hierarchical CLA implementation with a top-level Lookahead Carry Unit (LCU)
    that computes all inter-block carries in parallel using group generate and propagate signals.
    """
    cin = Bits(1)(0)

    # Compute all four 16-bit blocks once with cin and extract g, p
    # The 16-bit CLA function returns (sum, cout, group_g, group_p)
    # For the first block, we use actual cin
    s0, _, g0, p0 = carry_lookahead_adder_16bit(a[0:15], b[0:15], cin)

    # For blocks 1-3, we need their g and p values which don't depend on their cin input
    # But we also need their sums which DO depend on cin. So we compute with cin=0 first
    # to get g and p, then compute carries, then recompute sums with correct carries.
    # However, since we optimized carry_lookahead_adder_16bit to inline everything,
    # we can compute each block once with the correct carry-in.

    # Top-level Lookahead Carry Unit (LCU): compute all carries in parallel
    # But first we need g1, g2, g3 and p1, p2, p3 from blocks that don't have their final cin yet
    # We compute these with cin=0 since g and p don't depend on cin for the group signals
    _, _, g1, p1 = carry_lookahead_adder_16bit(a[16:31], b[16:31], Bits(1)(0))
    _, _, g2, p2 = carry_lookahead_adder_16bit(a[32:47], b[32:47], Bits(1)(0))
    _, _, g3, p3 = carry_lookahead_adder_16bit(a[48:63], b[48:63], Bits(1)(0))

    # Compute carries using the LCU equations
    c16 = g0 | (p0 & cin)
    c32 = g1 | (p1 & g0) | (p1 & p0 & cin)
    c48 = g2 | (p2 & g1) | (p2 & p1 & g0) | (p2 & p1 & p0 & cin)

    # Now compute sums for blocks 1-3 with correct carries
    s1, _, _, _ = carry_lookahead_adder_16bit(a[16:31], b[16:31], c16)
    s2, _, _, _ = carry_lookahead_adder_16bit(a[32:47], b[32:47], c32)
    s3, _, _, _ = carry_lookahead_adder_16bit(a[48:63], b[48:63], c48)

    result = concat(s3, concat(s2, concat(s1, s0)))

    return result


class WallaceTreeMul:
    """
    3-cycle Wallace Tree Multiplier with Carry-Lookahead Adder

    - Cycle 1 (EX_M1): Generate 32 partial products + compress 2 levels (32 → 22 → 15 rows)
    - Cycle 2 (EX_M2): Wallace Tree compression Levels 3-8 (15 → 2 rows)
    - Cycle 3 (EX_M3): Final addition using Carry-Lookahead Adder (CLA)
    """

    def __init__(self):
        # Pipeline stage registers
        # Stage 1 (EX_M1): Partial product generation + 2 levels of compression
        self.m1_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m1_op1 = RegArray(Bits(32), 1, initializer=[0])
        self.m1_op2 = RegArray(Bits(32), 1, initializer=[0])
        self.m1_op1_signed = RegArray(Bits(1), 1, initializer=[0])
        self.m1_op2_signed = RegArray(Bits(1), 1, initializer=[0])
        self.m1_result_high = RegArray(Bits(1), 1, initializer=[0])  # Whether to return high 32 bits
        self.m1_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register

        # Stage 2 (EX_M2): Wallace Tree compression (15 → 2 rows)
        # Store 15 intermediate rows from Stage 1 (after 2 levels of compression)
        self.m2_valid = RegArray(Bits(1), 1, initializer=[0])
        self.m2_result_high = RegArray(Bits(1), 1, initializer=[0])
        self.m2_rd = RegArray(Bits(5), 1, initializer=[0])  # Destination register
        # Signed multiplication correction for MULH
        self.m2_signed_correction = RegArray(Bits(32), 1, initializer=[0])
        # 15 intermediate rows from Stage 1 (after Level 1 and Level 2 compression)
        self.m2_row0 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row1 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row2 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row3 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row4 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row5 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row6 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row7 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row8 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row9 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row10 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row11 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row12 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row13 = RegArray(Bits(64), 1, initializer=[0])
        self.m2_row14 = RegArray(Bits(64), 1, initializer=[0])

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
        Execute EX_M1 stage: Partial Product Generation + 2 Levels of Compression

        This stage generates 32 partial products using AND gates, then performs
        Level 1 (32 → 22) and Level 2 (22 → 15) compression.
        """
        # Only process if stage 1 is valid
        with Condition(self.m1_valid[0] == Bits(1)(1)):
            # Read pipeline registers
            op1 = self.m1_op1[0]
            op2 = self.m1_op2[0]
            op1_signed = self.m1_op1_signed[0]
            op2_signed = self.m1_op2_signed[0]

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

            # =================================================================
            # Step 4: Wallace Tree Compression Level 1 (32 → 22 rows)
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
            # Level 1 output: 22 rows total (10 sum outputs: s1_0..s1_9, 10 carry outputs: c1_0..c1_9, 2 passthrough: pp30, pp31)

            # =================================================================
            # Step 5: Wallace Tree Compression Level 2 (22 → 15 rows)
            # =================================================================
            # Level 2: 22 → 15 rows (7 groups of 3, 1 passthrough)
            s2_0, c2_0 = full_adder_64bit(s1_0, c1_0, s1_1)
            s2_1, c2_1 = full_adder_64bit(c1_1, s1_2, c1_2)
            s2_2, c2_2 = full_adder_64bit(s1_3, c1_3, s1_4)
            s2_3, c2_3 = full_adder_64bit(c1_4, s1_5, c1_5)
            s2_4, c2_4 = full_adder_64bit(s1_6, c1_6, s1_7)
            s2_5, c2_5 = full_adder_64bit(c1_7, s1_8, c1_8)
            s2_6, c2_6 = full_adder_64bit(s1_9, c1_9, pp30)
            # Passthrough: pp31
            # Level 2 output: 15 rows total (7 sum outputs: s2_0..s2_6, 7 carry outputs: c2_0..c2_6, 1 passthrough: pp31)

            # =================================================================
            # Store 15 intermediate rows in stage 2 pipeline registers
            # =================================================================
            self.m2_valid[0] = Bits(1)(1)
            self.m2_result_high[0] = self.m1_result_high[0]
            self.m2_rd[0] = self.m1_rd[0]
            self.m2_signed_correction[0] = signed_correction

            # Store all 15 intermediate rows
            self.m2_row0[0] = s2_0
            self.m2_row1[0] = c2_0
            self.m2_row2[0] = s2_1
            self.m2_row3[0] = c2_1
            self.m2_row4[0] = s2_2
            self.m2_row5[0] = c2_2
            self.m2_row6[0] = s2_3
            self.m2_row7[0] = c2_3
            self.m2_row8[0] = s2_4
            self.m2_row9[0] = c2_4
            self.m2_row10[0] = s2_5
            self.m2_row11[0] = c2_5
            self.m2_row12[0] = s2_6
            self.m2_row13[0] = c2_6
            self.m2_row14[0] = pp31

            # Clear stage 1
            self.m1_valid[0] = Bits(1)(0)

    def cycle_m2(self):
        """
        Execute EX_M2 stage: Wallace Tree Compression Levels 3-8 (15 → 2 rows)

        This stage continues Wallace Tree compression from 15 rows down to 2 rows.
        """
        # Only process if stage 2 is valid
        with Condition(self.m2_valid[0] == Bits(1)(1)):

            # Read all 15 intermediate rows from pipeline registers
            # From Level 2 output: s2_0..s2_6, c2_0..c2_6, pp31
            s2_0 = self.m2_row0[0]
            c2_0 = self.m2_row1[0]
            s2_1 = self.m2_row2[0]
            c2_1 = self.m2_row3[0]
            s2_2 = self.m2_row4[0]
            c2_2 = self.m2_row5[0]
            s2_3 = self.m2_row6[0]
            c2_3 = self.m2_row7[0]
            s2_4 = self.m2_row8[0]
            c2_4 = self.m2_row9[0]
            s2_5 = self.m2_row10[0]
            c2_5 = self.m2_row11[0]
            s2_6 = self.m2_row12[0]
            c2_6 = self.m2_row13[0]
            pp31 = self.m2_row14[0]

            # =================================================================
            # Wallace Tree Compression Levels 3-8 (15 → 2 rows)
            # =================================================================

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
        using a carry-lookahead adder, with signed correction integrated via 3:2 compression.
        """
        # Only process if stage 3 is valid and result is not already ready
        with Condition((self.m3_valid[0] == Bits(1)(1)) & (self.m3_result_ready[0] == Bits(1)(0))):

            # Read the 2 final rows from pipeline registers
            s8_final = self.m3_row0[0]
            c8_final = self.m3_row1[0]
            signed_correction = self.m3_signed_correction[0]

            # =================================================================
            # Integrate signed correction using 3:2 compression
            # Instead of computing: product_64 = sum + carry, then high -= correction
            # We compute: product_64 = sum + carry + (-correction << 32)
            #
            # To subtract correction from high 32 bits, we add the two's complement:
            # -correction = ~correction + 1
            # We place this in bits [32:63] and handle the +1 in the carry row
            # =================================================================

            # Create the correction value as a 64-bit number positioned in high 32 bits
            # correction_neg_high represents ~signed_correction in bits [32:63]
            correction_inv = ~signed_correction  # Inverted bits for two's complement
            correction_neg_64 = concat(correction_inv, Bits(32)(0))  # Place in high 32 bits

            # For the +1 of two's complement, we add 1 at bit 32
            # This can be merged into the carry row at position 32
            # Create a 64-bit value with 1 at bit position 32 (i.e., 0x100000000)
            correction_plus_one = Bits(64)(0x100000000)  # 1 << 32

            # Use 3:2 compressor to merge s8_final, c8_final, and correction_neg_64
            s9_0, c9_0 = full_adder_64bit(s8_final, c8_final, correction_neg_64)

            # Use another 3:2 compressor to merge s9_0, c9_0, and correction_plus_one
            s_final, c_final = full_adder_64bit(s9_0, c9_0, correction_plus_one)

            # =================================================================
            # CLA (Carry-Lookahead Adder) - Final Addition
            # Now we have integrated the signed correction into the compression
            # =================================================================
            product_64 = carry_lookahead_adder_64bit(s_final, c_final)

            # Select which 32 bits to return based on operation type
            partial_low = product_64[0:31].bitcast(Bits(32))
            partial_high = product_64[32:63].bitcast(Bits(32))

            result = self.m3_result_high[0].select(
                partial_high,  # High 32 bits for MULH/MULHSU/MULHU
                partial_low  # Low 32 bits for MUL
            )

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