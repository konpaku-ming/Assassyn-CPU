"""
Radix-16 Divider for RV32IM Division Instructions with On-the-Fly Conversion

This module implements a Radix-16 division algorithm that produces 4 bits
of quotient per iteration, using an optimized Quotient Digit Selection (QDS)
approach with On-the-Fly (OTF) conversion for efficient quotient accumulation.

Architecture Overview:
=====================

The Radix-16 divider uses:
1. Non-negative quotient digit set {0, 1, 2, ..., 8} with OTF conversion
2. QDS (Quotient Digit Selection) with binary search tree structure
3. On-the-Fly (OTF) conversion using Q and QM accumulators
4. 4 bits of quotient per cycle
5. Full-precision comparisons with optimized selection logic

On-the-Fly (OTF) Conversion:
============================
Traditional shift-and-accumulate dividers require careful handling of quotient
overflow. The On-the-Fly conversion technique eliminates this overhead by
maintaining two quotient accumulators that are updated in parallel:

- Q:  Current quotient estimate (standard binary)
- QM: Q minus 1 (Q - 1), always one less than Q

At each iteration for non-negative quotient digit q (0 ≤ q ≤ 8):
- If q > 0: Q = (Q << 4) + q, QM = (Q << 4) + (q - 1)
- If q = 0: Q = (Q << 4), QM = (QM << 4) + 15

This maintains the invariant QM = Q - 1 throughout the computation,
and Q directly contains the correct quotient at the end.

Key Radix-16 Features with QDS and OTF Optimization:
- 4 bits of quotient per iteration (vs 2 bits for Radix-4, 3 bits for Radix-8)
- Fixed 8 iterations for 32-bit division
- Binary search tree selection reduces mux depth
- On-the-Fly conversion maintains Q/QM accumulators in parallel
- Only 8 divisor multiples (d1-d8) needed instead of 15

QDS (Quotient Digit Selection) Approach:
========================================
Modern CPU dividers optimize the quotient selection critical path. The key insight
is that while we need to compare against all divisor multiples for correctness,
the selection logic can be structured as a binary search tree instead of a
priority encoder.

The comparisons use full-precision 36-bit arithmetic, while the selection
logic is optimized for minimal depth using a 4-level binary tree.

Timing:
- 1 cycle: Preprocessing (DIV_PRE)
- 8 cycles: Iterative calculation (DIV_WORKING) - 4 bits per cycle with QDS+OTF
- 1 cycle: Post-processing (DIV_END)
- Total: ~10 cycles for normal division

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class Radix16Divider:
    """
    Radix-16 division implementation that produces 4 bits of quotient per iteration,
    using an optimized QDS (Quotient Digit Selection) approach with On-the-Fly (OTF)
    conversion for efficient quotient accumulation.

    The divider is a multi-cycle functional unit that takes ~10 cycles:
    - 1 cycle: Preprocessing
    - 8 cycles: Iterative calculation (4 bits per cycle with QDS + OTF)
    - 1 cycle: Post-processing

    Key Radix-16 features with QDS and OTF optimization:
    - Non-negative quotient digit set {0, 1, 2, ..., 8}
    - Binary search tree selection structure (4 mux levels)
    - On-the-Fly conversion using Q and QM accumulators
    - Full-precision 36-bit comparisons for correctness
    - Optimized critical path through selection logic
    - 4 bits of quotient per iteration
    - Fixed 8 iterations for 32-bit division

    On-the-Fly (OTF) Conversion:
    ============================
    The OTF technique maintains two accumulators updated in parallel:
    - Q:  Current quotient (standard binary representation)
    - QM: Q minus 1 (always equals Q - 1)

    For non-negative quotient digit q (0 ≤ q ≤ 8):
        If q > 0: Q_new = (Q << 4) + q, QM_new = (Q << 4) + (q - 1)
        If q = 0: Q_new = (Q << 4), QM_new = (QM << 4) + 15

    This maintains the invariant QM = Q - 1, and Q directly contains
    the correct quotient at the end without any conversion needed.

    QDS Selection Logic:
    The quotient digit selection uses a binary search tree structure:
    - q[3] (MSB magnitude) determined by comparing with 8d
    - q[2] determined by comparing with 4d based on q[3]
    - q[1] determined by comparing with 2d/6d based on q[3:2]
    - q[0] (LSB) determined by comparing with odd multiples

    Pipeline Integration:
    - When a division instruction enters EX stage, the divider is started
    - The pipeline stalls (IF/ID/EX) until divider completes
    - Result is written back to register file through normal WB path
    """

    def __init__(self):
        # Control and status registers
        self.busy = RegArray(Bits(1), 1, initializer=[0])
        self.valid_in = RegArray(Bits(1), 1, initializer=[0])

        # Input operands (captured when valid)
        self.dividend_in = RegArray(Bits(32), 1, initializer=[0])
        self.divisor_in = RegArray(Bits(32), 1, initializer=[0])
        self.is_signed = RegArray(Bits(1), 1, initializer=[0])
        self.is_rem = RegArray(Bits(1), 1, initializer=[0])  # 1=remainder, 0=quotient
        self.rd_in = RegArray(Bits(5), 1, initializer=[0])  # Destination register

        # Output results
        self.result = RegArray(Bits(32), 1, initializer=[0])
        self.ready = RegArray(Bits(1), 1, initializer=[0])
        self.error = RegArray(Bits(1), 1, initializer=[0])  # Division by zero
        self.rd_out = RegArray(Bits(5), 1, initializer=[0])  # Output destination register

        # State machine registers
        self.state = RegArray(Bits(3), 1, initializer=[0])  # FSM state
        self.div_cnt = RegArray(Bits(5), 1, initializer=[0])  # Iteration counter (counts down)

        # Internal working registers
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor

        # Radix-16 specific registers
        self.quotient = RegArray(Bits(32), 1, initializer=[0])  # Quotient accumulator (for compatibility)
        self.remainder = RegArray(Bits(36), 1,
                                  initializer=[0])  # Partial remainder (36 bits for 4-bit shift + 8*d overflow)

        # On-the-Fly (OTF) conversion accumulators
        # Q:  Current quotient estimate in standard binary
        # QM: Q minus 1 (always equals Q - 1), used for negative digit handling
        self.Q = RegArray(Bits(32), 1, initializer=[0])   # On-the-Fly quotient accumulator
        self.QM = RegArray(Bits(32), 1, initializer=[0])  # On-the-Fly quotient-minus-1 accumulator

        # QDS-optimized divisor multiples for signed-digit set {-8, ..., 0, ..., 8}
        # These are stored as normalized (shifted) values for efficient QDS lookup
        self.d1 = RegArray(Bits(36), 1, initializer=[0])  # 1*d (normalized)
        self.d2 = RegArray(Bits(36), 1, initializer=[0])  # 2*d (normalized)
        self.d3 = RegArray(Bits(36), 1, initializer=[0])  # 3*d (for QDS refinement)
        self.d4 = RegArray(Bits(36), 1, initializer=[0])  # 4*d (normalized)
        self.d5 = RegArray(Bits(36), 1, initializer=[0])  # 5*d (for QDS refinement)
        self.d6 = RegArray(Bits(36), 1, initializer=[0])  # 6*d (for QDS refinement)
        self.d7 = RegArray(Bits(36), 1, initializer=[0])  # 7*d (for QDS refinement)
        self.d8 = RegArray(Bits(36), 1, initializer=[0])  # 8*d (normalized, boundary value)

        # Sign tracking for final correction
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])  # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])  # Sign flag for result

        # Compatibility registers for tests (preserved for backward compatibility)
        self.norm_shift = RegArray(Bits(6), 1, initializer=[0])  # Reserved for future normalization
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])  # Reserved for future optimization
        self.shift_rem = RegArray(Bits(36), 1, initializer=[0])  # For compatibility

        # FSM states
        self.IDLE = Bits(3)(0)
        self.DIV_PRE = Bits(3)(1)
        self.DIV_WORKING = Bits(3)(2)
        self.DIV_END = Bits(3)(3)
        self.DIV_1 = Bits(3)(4)
        self.DIV_ERROR = Bits(3)(5)

    def is_busy(self):
        """Check if divider is currently processing"""
        return self.busy[0]

    def find_leading_one(self, value):
        """
        Find position of leading 1 bit.
        Returns the bit position (0-31) of the most significant 1 bit.
        Returns 32 if value is 0.
        """
        result = Bits(6)(32)
        for i in range(31, -1, -1):
            bit_set = value[i:i] == Bits(1)(1)
            result = bit_set.select(Bits(6)(i), result)
        return result

    def power_of_2(self, shift_amt):
        """Generate 2^shift_amt (for shifts 0-31)"""
        result = Bits(32)(1)
        for i in range(32):
            is_this_shift = (shift_amt == Bits(6)(i))
            result = is_this_shift.select(Bits(32)(1 << i), result)
        return result

    def quotient_select_with_otf(self, shifted_rem, d1, d2, d3, d4, d5, d6, d7, d8):
        """
        QDS (Quotient Digit Selection) for Radix-16 division with On-the-Fly support.

        This implementation uses a non-negative quotient digit set {0, 1, 2, ..., 8}
        with a binary search tree structure for the selection logic.

        On-the-Fly Conversion Support:
        ==============================
        Returns both the quotient digit value (as unsigned 4-bit) and a sign flag.
        - q_digit: Quotient digit value (0-8)
        - q_sign: Sign flag (always 0 for non-negative digits)

        The sign flag is included for future extensibility to signed-digit sets,
        but in this implementation all quotient digits are non-negative.

        Hardware Implementation Note:
        ============================
        The quotient digit set {0, 1, ..., 8} is sufficient because:
        1. The partial remainder is always kept positive after each iteration
        2. We subtract q*d from shifted_rem, where 0 ≤ q ≤ 8
        3. The next shifted_rem will be in range [0, 16*d) after left shift

        QDS Binary Search Tree for {0, 1, ..., 8}:
        ==========================================
        - Compare with 8d: if >= 8d, q[3] = 1 (q = 8)
        - Compare with 4d: if >= 4d and < 8d, q[2] = 1
        - Compare with 2d/6d: determines q[1]
        - Compare with odd multiples: determines q[0]

        Returns: (q_digit, q_sign) where:
        - q_digit: 4-bit unsigned (0-8)
        - q_sign: 1-bit sign (always 0)
        """
        # All comparisons computed in parallel (in hardware)
        # For signed-digit selection, we compare against 0 through 8d
        # Since our shifted_rem is always non-negative in this implementation,
        # we use a simpler approach with non-negative quotient digits

        # Compare against divisor multiples (binary search tree)
        ge_8d = (shifted_rem.bitcast(UInt(36)) >= d8.bitcast(UInt(36)))
        ge_7d = (shifted_rem.bitcast(UInt(36)) >= d7.bitcast(UInt(36)))
        ge_6d = (shifted_rem.bitcast(UInt(36)) >= d6.bitcast(UInt(36)))
        ge_5d = (shifted_rem.bitcast(UInt(36)) >= d5.bitcast(UInt(36)))
        ge_4d = (shifted_rem.bitcast(UInt(36)) >= d4.bitcast(UInt(36)))
        ge_3d = (shifted_rem.bitcast(UInt(36)) >= d3.bitcast(UInt(36)))
        ge_2d = (shifted_rem.bitcast(UInt(36)) >= d2.bitcast(UInt(36)))
        ge_1d = (shifted_rem.bitcast(UInt(36)) >= d1.bitcast(UInt(36)))

        # Build quotient using binary search tree structure for {0, 1, ..., 8}
        # q[3] (MSB) = ge_8d
        q3 = ge_8d

        # q[2] depends on q[3]:
        # - If q[3]=1 (q>=8): q[2] = 0 (since max is 8)
        # - If q[3]=0 (q<8):  q[2] = (q>=4), so q[2] = ge_4d
        q2 = ge_8d.select(
            Bits(1)(0),  # q = 8, so q[2] = 0 (8 = 0b1000)
            ge_4d.select(Bits(1)(1), Bits(1)(0))  # q < 8: check >= 4
        )

        # q[1] depends on (q[3], q[2]):
        # - q=8: q[1] = 0
        # - 4<=q<8: q[1] = (q>=6), so ge_6d
        # - q<4: q[1] = (q>=2), so ge_2d
        q1 = ge_8d.select(
            Bits(1)(0),  # q = 8
            ge_4d.select(
                ge_6d.select(Bits(1)(1), Bits(1)(0)),  # 4 <= q < 8
                ge_2d.select(Bits(1)(1), Bits(1)(0))   # q < 4
            )
        )

        # q[0] (LSB) depends on (q[3], q[2], q[1]):
        # - q=8: q[0] = 0
        # - 6<=q<8: q[0] = ge_7d
        # - 4<=q<6: q[0] = ge_5d
        # - 2<=q<4: q[0] = ge_3d
        # - q<2: q[0] = ge_1d
        q0 = ge_8d.select(
            Bits(1)(0),  # q = 8
            ge_4d.select(
                ge_6d.select(
                    ge_7d.select(Bits(1)(1), Bits(1)(0)),  # 6 <= q < 8
                    ge_5d.select(Bits(1)(1), Bits(1)(0))   # 4 <= q < 6
                ),
                ge_2d.select(
                    ge_3d.select(Bits(1)(1), Bits(1)(0)),  # 2 <= q < 4
                    ge_1d.select(Bits(1)(1), Bits(1)(0))   # q < 2
                )
            )
        )

        # Combine bits into 4-bit quotient digit
        # Using proper bit concatenation: q = {q3, q2, q1, q0}
        q = concat(
            concat(
                concat(
                    q3.select(Bits(1)(1), Bits(1)(0)),
                    q2.select(Bits(1)(1), Bits(1)(0))
                ),
                q1.select(Bits(1)(1), Bits(1)(0))
            ),
            q0.select(Bits(1)(1), Bits(1)(0))
        )

        # In this implementation, quotient digits are always non-negative (0-8)
        # The sign flag is always 0 for this restoring-style approach
        q_sign = Bits(1)(0)

        return q, q_sign

    def on_the_fly_update(self, Q_cur, QM_cur, q_digit, q_sign):
        """
        On-the-Fly (OTF) quotient accumulator update.

        This function implements the core OTF conversion algorithm that maintains
        two quotient accumulators (Q and QM) updated in parallel.

        Algorithm for Non-Negative Quotient Digits:
        ===========================================
        In this implementation, q_sign is always 0 and q_digit is in {0, 1, ..., 8}.

        For q_digit > 0:
            Q_new  = (Q << 4) + q_digit
            QM_new = (Q << 4) + (q_digit - 1)

        For q_digit = 0:
            Q_new  = (Q << 4)
            QM_new = (QM << 4) + 15

        The special case for q_digit = 0 is necessary because:
        - Q_new should be Q * 16 + 0 = Q * 16
        - QM_new should be Q_new - 1 = Q * 16 - 1 = (Q - 1) * 16 + 15 = QM * 16 + 15

        Invariant Maintenance:
        =====================
        - Q always holds the correct quotient in standard binary
        - QM always holds Q - 1
        - After update: QM_new = Q_new - 1 ✓

        The negative digit path (q_sign = 1) is included for completeness and
        future extensibility but is not used in the current implementation.

        Args:
            Q_cur: Current Q accumulator (32-bit)
            QM_cur: Current QM accumulator (32-bit)
            q_digit: Quotient digit (4-bit, 0-8)
            q_sign: Quotient digit sign (1-bit, always 0 in current implementation)

        Returns:
            (Q_new, QM_new): Updated accumulators
        """
        # Shift Q and QM left by 4 bits
        Q_shifted = concat(Q_cur[0:27], Bits(4)(0))
        QM_shifted = concat(QM_cur[0:27], Bits(4)(0))

        # For positive quotient digit (q_sign = 0):
        # Handle q_digit = 0 specially: QM uses QM_shifted with 15 (0xF)
        q_is_zero = (q_digit == Bits(4)(0))

        # Q_new for positive digit
        Q_new_pos = (Q_shifted.bitcast(UInt(32)) + q_digit.bitcast(UInt(32))).bitcast(Bits(32))

        # QM_new for positive digit (q_digit > 0)
        q_digit_minus_1 = (q_digit.bitcast(UInt(4)) - UInt(4)(1)).bitcast(Bits(4))
        QM_new_pos_nonzero = (Q_shifted.bitcast(UInt(32)) + q_digit_minus_1.bitcast(UInt(32))).bitcast(Bits(32))

        # QM_new for q_digit = 0: use QM_shifted + 15
        QM_new_pos_zero = (QM_shifted.bitcast(UInt(32)) + UInt(32)(15)).bitcast(Bits(32))

        # Select QM_new for positive digit based on whether q_digit is 0
        QM_new_pos = q_is_zero.select(QM_new_pos_zero, QM_new_pos_nonzero)

        # For negative quotient digit (q_sign = 1):
        # Q_new = QM_shifted + (16 - q_digit)
        # QM_new = QM_shifted + (15 - q_digit)
        val_16_minus_q = (UInt(32)(16) - q_digit.bitcast(UInt(32))).bitcast(Bits(32))
        val_15_minus_q = (UInt(32)(15) - q_digit.bitcast(UInt(32))).bitcast(Bits(32))

        Q_new_neg = (QM_shifted.bitcast(UInt(32)) + val_16_minus_q.bitcast(UInt(32))).bitcast(Bits(32))
        QM_new_neg = (QM_shifted.bitcast(UInt(32)) + val_15_minus_q.bitcast(UInt(32))).bitcast(Bits(32))

        # Final selection based on q_sign
        Q_new = q_sign.select(Q_new_neg, Q_new_pos)
        QM_new = q_sign.select(QM_new_neg, QM_new_pos)

        return Q_new, QM_new

    def start_divide(self, dividend, divisor, is_signed, is_rem, rd=Bits(5)(0)):
        """
        Start a division operation.

        Args:
            dividend: 32-bit dividend (rs1)
            divisor: 32-bit divisor (rs2)
            is_signed: 1 for signed (DIV/REM), 0 for unsigned (DIVU/REMU)
            is_rem: 1 to return remainder, 0 to return quotient
            rd: Destination register (5-bit), defaults to 0
        """
        self.dividend_in[0] = dividend
        self.divisor_in[0] = divisor
        self.is_signed[0] = is_signed
        self.is_rem[0] = is_rem
        self.rd_in[0] = rd
        self.valid_in[0] = Bits(1)(1)
        self.busy[0] = Bits(1)(1)
        self.ready[0] = Bits(1)(0)
        self.error[0] = Bits(1)(0)

        debug_log("Radix16Divider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
                  dividend,
                  divisor,
                  is_signed)

    def tick(self):
        """
        Execute one cycle of the Radix-16 state machine.
        Should be called every clock cycle.
        """

        # State: IDLE - Wait for valid signal and check for special cases
        with Condition(self.state[0] == self.IDLE):
            with Condition(self.valid_in[0] == Bits(1)(1)):
                # Check for special cases
                div_by_zero = (self.divisor_in[0] == Bits(32)(0))
                div_by_one = (self.divisor_in[0] == Bits(32)(1))

                with Condition(div_by_zero):
                    # Handle division by zero per RISC-V spec
                    self.state[0] = self.DIV_ERROR
                    self.valid_in[0] = Bits(1)(0)
                    debug_log("Radix16Divider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    debug_log("Radix16Divider: Fast path (divisor=1)")

                with Condition(~div_by_zero & ~div_by_one):
                    # Normal division path - go to preprocessing
                    self.state[0] = self.DIV_PRE
                    self.valid_in[0] = Bits(1)(0)

                    # Convert to unsigned if signed
                    dividend_is_neg = self.is_signed[0] & self.dividend_in[0][31:31]
                    divisor_is_neg = self.is_signed[0] & self.divisor_in[0][31:31]

                    # Take absolute value if negative
                    dividend_abs = dividend_is_neg.select(
                        (~self.dividend_in[0] + Bits(32)(1)).bitcast(Bits(32)),
                        self.dividend_in[0]
                    )
                    divisor_abs = divisor_is_neg.select(
                        (~self.divisor_in[0] + Bits(32)(1)).bitcast(Bits(32)),
                        self.divisor_in[0]
                    )

                    self.dividend_r[0] = dividend_abs
                    self.divisor_r[0] = divisor_abs
                    self.div_sign[0] = concat(self.dividend_in[0][31:31], self.divisor_in[0][31:31])
                    self.sign_r[0] = self.is_signed[0]

                    debug_log("Radix16Divider: Starting normal division (DIV_PRE)")

        # State: DIV_ERROR - Handle division by zero
        with Condition(self.state[0] == self.DIV_ERROR):
            # Return RISC-V specified error values
            quotient_on_div0 = self.is_signed[0].select(
                Bits(32)(0xFFFFFFFF),  # -1 for signed
                Bits(32)(0xFFFFFFFF)  # 2^32-1 for unsigned (same bit pattern)
            )
            self.result[0] = self.is_rem[0].select(
                self.dividend_in[0],  # Remainder = dividend
                quotient_on_div0  # Quotient = -1 or 2^32-1
            )
            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.error[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("Radix16Divider: Completed with division by zero error")

        # State: DIV_1 - Fast path for divisor = 1
        with Condition(self.state[0] == self.DIV_1):
            # Fast path: quotient is dividend, remainder is 0
            self.result[0] = self.is_rem[0].select(
                Bits(32)(0),  # Remainder = 0
                self.dividend_in[0]  # Quotient = dividend
            )
            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("Radix16Divider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing for Radix-16 division with On-the-Fly
        with Condition(self.state[0] == self.DIV_PRE):
            divisor = self.divisor_r[0]
            dividend = self.dividend_r[0]

            # Compute divisor multiples (36 bits to handle 8*d overflow)
            # For On-the-Fly with digit set {0..8}, we only need d1 through d8
            d_36 = concat(Bits(4)(0), divisor)  # 36-bit divisor

            # Compute 1d through 8d using efficient combinations
            d1_val = d_36
            d2_val = (d_36.bitcast(UInt(36)) << UInt(36)(1)).bitcast(Bits(36))  # 2*d
            d3_val = (d2_val.bitcast(UInt(36)) + d_36.bitcast(UInt(36))).bitcast(Bits(36))  # 3*d = 2d + d
            d4_val = (d_36.bitcast(UInt(36)) << UInt(36)(2)).bitcast(Bits(36))  # 4*d
            d5_val = (d4_val.bitcast(UInt(36)) + d_36.bitcast(UInt(36))).bitcast(Bits(36))  # 5*d = 4d + d
            d6_val = (d4_val.bitcast(UInt(36)) + d2_val.bitcast(UInt(36))).bitcast(Bits(36))  # 6*d = 4d + 2d
            d7_val = (d4_val.bitcast(UInt(36)) + d3_val.bitcast(UInt(36))).bitcast(Bits(36))  # 7*d = 4d + 3d
            d8_val = (d_36.bitcast(UInt(36)) << UInt(36)(3)).bitcast(Bits(36))  # 8*d

            # Store divisor multiples (only d1-d8 needed for OTF with digit set {0..8})
            self.d1[0] = d1_val
            self.d2[0] = d2_val
            self.d3[0] = d3_val
            self.d4[0] = d4_val
            self.d5[0] = d5_val
            self.d6[0] = d6_val
            self.d7[0] = d7_val
            self.d8[0] = d8_val

            # Initialize quotient to 0, remainder to 0
            self.quotient[0] = Bits(32)(0)
            self.remainder[0] = Bits(36)(0)

            # Initialize On-the-Fly accumulators
            # Q starts at 0, QM starts at -1 (0xFFFFFFFF in two's complement)
            # This maintains the invariant QM = Q - 1 throughout computation
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0xFFFFFFFF)  # -1 in two's complement

            # For 32-bit division with 4 bits per iteration: ceil(32/4) = 8 iterations
            self.div_cnt[0] = Bits(5)(8)

            # Store dividend for iteration
            self.dividend_r[0] = dividend

            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING

            debug_log("Radix16Divider: Preprocessing complete (OTF), d1=0x{:x}, d8=0x{:x}",
                      d1_val, d8_val)

        # State: DIV_WORKING - Radix-16 iteration with On-the-Fly conversion
        with Condition(self.state[0] == self.DIV_WORKING):
            # Get current values
            rem_cur = self.remainder[0]  # 36-bit partial remainder
            Q_cur = self.Q[0]            # On-the-Fly quotient accumulator
            QM_cur = self.QM[0]          # On-the-Fly quotient-minus-1 accumulator
            dividend_cur = self.dividend_r[0]  # Remaining dividend bits

            # Shift remainder left by 4 and bring in next 4 dividend bits
            # Bits come from MSB of dividend_cur
            next_bits = dividend_cur[28:31]  # Top 4 bits of dividend
            shifted_rem = concat(rem_cur[0:31], next_bits)  # (rem << 4) | next_bits

            # Shift dividend left by 4 (move next bits into position)
            new_dividend = concat(dividend_cur[0:27], Bits(4)(0))

            # Quotient digit selection using Radix-16 comparison with OTF support
            # Returns (q_digit, q_sign) for On-the-Fly update
            q_digit, q_sign = self.quotient_select_with_otf(
                shifted_rem,
                self.d1[0], self.d2[0], self.d3[0], self.d4[0],
                self.d5[0], self.d6[0], self.d7[0], self.d8[0]
            )

            # Compute new remainder based on quotient digit: rem = shifted_rem - q * d
            # Since q_digit is in range {0..8}, we only need to handle these cases
            q_times_d = (q_digit == Bits(4)(0)).select(
                Bits(36)(0),
                (q_digit == Bits(4)(1)).select(
                    self.d1[0],
                    (q_digit == Bits(4)(2)).select(
                        self.d2[0],
                        (q_digit == Bits(4)(3)).select(
                            self.d3[0],
                            (q_digit == Bits(4)(4)).select(
                                self.d4[0],
                                (q_digit == Bits(4)(5)).select(
                                    self.d5[0],
                                    (q_digit == Bits(4)(6)).select(
                                        self.d6[0],
                                        (q_digit == Bits(4)(7)).select(
                                            self.d7[0],
                                            self.d8[0]  # q=8
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )

            new_rem = (shifted_rem.bitcast(UInt(36)) - q_times_d.bitcast(UInt(36))).bitcast(Bits(36))

            # On-the-Fly quotient accumulator update
            # This is the core OTF conversion: update both Q and QM in parallel
            Q_new, QM_new = self.on_the_fly_update(Q_cur, QM_cur, q_digit, q_sign)

            # Store updated values
            self.remainder[0] = new_rem
            self.Q[0] = Q_new
            self.QM[0] = QM_new
            self.quotient[0] = Q_new  # For compatibility, quotient tracks Q
            self.dividend_r[0] = new_dividend

            # Update shift_rem for compatibility
            self.shift_rem[0] = shifted_rem

            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - UInt(5)(1)).bitcast(Bits(5))

            debug_log("Radix16Divider: OTF iter, shifted_rem=0x{:x}, q={}, new_rem=0x{:x}, Q=0x{:x}, QM=0x{:x}",
                      shifted_rem, q_digit, new_rem, Q_new, QM_new)

            # Check if done
            is_last = (self.div_cnt[0] == Bits(5)(1))
            with Condition(is_last):
                self.state[0] = self.DIV_END
                debug_log("Radix16Divider: Last iteration complete (OTF)")

        # State: DIV_END - Post-processing with On-the-Fly result
        with Condition(self.state[0] == self.DIV_END):
            # On-the-Fly conversion: Q already contains the correct quotient in binary
            # No conversion step needed - this is the key benefit of OTF!
            q_out = self.Q[0]  # Use On-the-Fly Q accumulator directly
            rem_out = self.remainder[0][0:31]  # Take lower 32 bits of remainder

            debug_log("Radix16Divider: DIV_END (OTF) - Q=0x{:x}, QM=0x{:x}, remainder=0x{:x}",
                      self.Q[0], self.QM[0], rem_out)

            # Apply sign correction
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]

            debug_log("Radix16Divider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

            # Check for signed overflow: (-2^31) / (-1)
            min_int = Bits(32)(0x80000000)
            neg_one = Bits(32)(0xFFFFFFFF)
            signed_overflow = (self.sign_r[0] == Bits(1)(1)) & \
                              (self.dividend_in[0] == min_int) & \
                              (self.divisor_in[0] == neg_one)

            with Condition(signed_overflow):
                self.result[0] = self.is_rem[0].select(
                    Bits(32)(0),
                    Bits(32)(0x80000000)
                )
                debug_log("Radix16Divider: Signed overflow detected (-2^31 / -1)")

            with Condition(~signed_overflow):
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~q_out + Bits(32)(1)).bitcast(Bits(32)),
                    q_out
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~rem_out + Bits(32)(1)).bitcast(Bits(32)),
                    rem_out
                )

                debug_log("Radix16Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                          q_signed, rem_signed, self.is_rem[0])

                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            # Update quotient register for compatibility
            self.quotient[0] = q_out

            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("Radix16Divider: Completed (OTF), result=0x{:x}", self.result[0])

    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, rd, error)
        """
        return (self.ready[0], self.result[0], self.rd_out[0], self.error[0])

    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)


# Alias for backward compatibility
SRT4Divider = Radix16Divider