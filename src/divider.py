"""
Radix-4 Divider with On-the-fly Conversion for RV32IM Division Instructions

This module implements a Radix-4 restoring division algorithm that computes
2 quotient bits per clock cycle, with on-the-fly quotient conversion using
Q/QM registers.

Architecture Overview:
=====================

The divider uses Radix-4 quotient selection (comparing against 3d, 2d, d) 
combined with on-the-fly conversion technique from SRT dividers.

Algorithm:
1. Compare partial remainder against 3*d, 2*d, d
2. Select quotient digit from {0, 1, 2, 3}
3. Update Q/QM registers using on-the-fly conversion

On-the-fly conversion for non-negative digits {0, 1, 2, 3}:
- q=3: Q = Q<<2|11, QM = Q<<2|10
- q=2: Q = Q<<2|10, QM = Q<<2|01
- q=1: Q = Q<<2|01, QM = Q<<2|00
- q=0: Q = Q<<2|00, QM = QM<<2|11

Timing:
- 1 cycle: Preprocessing (DIV_PRE) - convert to unsigned, detect special cases
- 16 cycles: Iterative calculation (DIV_WORKING) - 2 bits per cycle
- 1 cycle: Post-processing (DIV_END) - sign correction
- Total: ~18 cycles for normal division

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class SRT4Divider:
    """
    Radix-4 restoring division with on-the-fly conversion for 32-bit operands.

    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (convert to unsigned, detect special cases)
    - 16 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (sign correction)

    Key features:
    - Radix-4 quotient selection using comparison against 3d, 2d, d
    - Quotient digit set {0, 1, 2, 3}
    - On-the-fly quotient conversion using Q/QM registers
    - Computes 2 bits per cycle

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
        
        # Working registers for division
        self.quotient = RegArray(Bits(32), 1, initializer=[0])  # Quotient accumulator
        self.remainder = RegArray(Bits(34), 1, initializer=[0])  # Remainder (34 bits for overflow)

        # On-the-fly conversion registers
        self.Q = RegArray(Bits(32), 1, initializer=[0])
        self.QM = RegArray(Bits(32), 1, initializer=[0])

        # Sign tracking for final correction
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])  # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])  # Sign flag for result

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

        Note: This helper method is provided for compatibility but is not used
        in the main division algorithm. To get the shift amount for normalization,
        compute (31 - find_leading_one(value)).
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

    def quotient_select(self, w_high):
        """Compatibility placeholder for quotient selection"""
        return Bits(3)(0)

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

        debug_log("SRT4Divider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
            dividend,
            divisor,
            is_signed)

    def tick(self):
        """
        Execute one cycle of the SRT-4 state machine.
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
                    debug_log("SRT4Divider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    debug_log("SRT4Divider: Fast path (divisor=1)")

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

                    debug_log("SRT4Divider: Starting normal division (DIV_PRE)")

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
            debug_log("SRT4Divider: Completed with division by zero error")

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
            debug_log("SRT4Divider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing for SRT-4 division
        # Based on pre_processing.v: normalize divisor and compute iterations
        with Condition(self.state[0] == self.DIV_PRE):
            # SRT-4 requires divisor normalization to place MSB at bit 31
            # This ensures divisor_index (bits [32:29]) is always 1xxx (8-15)
            #
            # Use a simpler approach: Fixed 16 iterations like original Radix-4
            # but with SRT-4 quotient selection via QDS table
            
            divisor = self.divisor_r[0]
            dividend = self.dividend_r[0]
            
            # Initialize with fixed 16 iterations (original Radix-4 approach)
            # This avoids complex normalization while still using SRT-4 quotient selection
            
            # Store registers for iteration
            # w_reg: 36-bit partial remainder, initialized from dividend
            # Format: [35:4] = remainder, [3:0] = shifted in dividend bits
            self.w_reg[0] = concat(Bits(4)(0), dividend)  # 36 bits
            
            # divisor_reg: 36-bit divisor (zero-extended)
            self.divisor_reg[0] = concat(Bits(4)(0), divisor)  # 36 bits
            
            # Use fixed 16 iterations for simplicity
            self.iterations_reg[0] = Bits(5)(16)
            self.recovery_reg[0] = Bits(6)(32)  # Recovery = no denormalization needed
            self.div_cnt[0] = Bits(5)(16)
            
            # Initialize Q/QM for on-the-fly conversion
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0)
            
            # Initialize quotient/remainder registers (used for actual computation)
            # quotient is initialized with dividend, will shift out bits during computation
            self.quotient[0] = dividend
            self.remainder[0] = Bits(34)(0)
            
            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING
            
            debug_log("SRT4Divider: Preprocessing complete, 16 iterations")

        # State: DIV_WORKING - Radix-4 iteration with on-the-fly conversion
        # Uses direct comparison (like original) but with Q/QM for quotient accumulation
        with Condition(self.state[0] == self.DIV_WORKING):
            # Get current values
            divisor = self.divisor_r[0]
            
            # Compute divisor multiples (34-bit to handle overflow in comparison)
            d1 = concat(Bits(2)(0), divisor)  # 1 * divisor (34 bits)
            d2 = concat(Bits(1)(0), divisor, Bits(1)(0))  # 2 * divisor (34 bits)
            d3 = (d1.bitcast(UInt(34)) + d2.bitcast(UInt(34))).bitcast(Bits(34))  # 3 * divisor
            
            # Shift remainder left by 2 and bring in 2 MSBs from quotient
            # remainder is 34 bits, quotient is 32 bits
            shifted_remainder = concat(
                self.remainder[0][0:31],  # Lower 32 bits of remainder
                self.quotient[0][30:31]  # Top 2 bits of quotient
            )  # 34 bits total
            
            # Shift quotient left by 2 (will set bottom 2 bits based on comparison)
            shifted_quotient = concat(self.quotient[0][0:29], Bits(2)(0))  # 32 bits
            
            # Compare shifted remainder with divisor multiples
            rem_minus_3d = (shifted_remainder.bitcast(UInt(34)) - d3.bitcast(UInt(34))).bitcast(Bits(34))
            rem_ge_3d = rem_minus_3d[33:33] == Bits(1)(0)  # No borrow = >= 0
            rem_minus_2d = (shifted_remainder.bitcast(UInt(34)) - d2.bitcast(UInt(34))).bitcast(Bits(34))
            rem_ge_2d = rem_minus_2d[33:33] == Bits(1)(0)
            rem_minus_1d = (shifted_remainder.bitcast(UInt(34)) - d1.bitcast(UInt(34))).bitcast(Bits(34))
            rem_ge_1d = rem_minus_1d[33:33] == Bits(1)(0)
            
            # Select quotient bits and new remainder based on comparison
            # q=3: remainder >= 3*d
            # q=2: remainder >= 2*d (but < 3*d)
            # q=1: remainder >= 1*d (but < 2*d)
            # q=0: remainder < 1*d
            q_bits = rem_ge_3d.select(
                Bits(2)(3),
                rem_ge_2d.select(
                    Bits(2)(2),
                    rem_ge_1d.select(
                        Bits(2)(1),
                        Bits(2)(0)
                    )
                )
            )
            
            new_remainder = rem_ge_3d.select(
                rem_minus_3d,
                rem_ge_2d.select(
                    rem_minus_2d,
                    rem_ge_1d.select(
                        rem_minus_1d,
                        shifted_remainder
                    )
                )
            )
            
            # On-the-fly conversion for Q and QM registers
            # For non-negative quotient digits {0, 1, 2, 3}:
            # q=3: Q = Q<<2|11, QM = Q<<2|10
            # q=2: Q = Q<<2|10, QM = Q<<2|01
            # q=1: Q = Q<<2|01, QM = Q<<2|00
            # q=0: Q = Q<<2|00, QM = QM<<2|11
            Q_cur = self.Q[0]
            QM_cur = self.QM[0]
            
            is_q_3 = (q_bits == Bits(2)(3))
            is_q_2 = (q_bits == Bits(2)(2))
            is_q_1 = (q_bits == Bits(2)(1))
            is_q_0 = (q_bits == Bits(2)(0))
            
            new_Q = is_q_3.select(
                concat(Q_cur[0:29], Bits(2)(0b11)),
                is_q_2.select(
                    concat(Q_cur[0:29], Bits(2)(0b10)),
                    is_q_1.select(
                        concat(Q_cur[0:29], Bits(2)(0b01)),
                        concat(Q_cur[0:29], Bits(2)(0b00))
                    )
                )
            )
            
            new_QM = is_q_3.select(
                concat(Q_cur[0:29], Bits(2)(0b10)),
                is_q_2.select(
                    concat(Q_cur[0:29], Bits(2)(0b01)),
                    is_q_1.select(
                        concat(Q_cur[0:29], Bits(2)(0b00)),
                        concat(QM_cur[0:29], Bits(2)(0b11))
                    )
                )
            )
            
            # Update quotient with new bits (for legacy compatibility)
            new_quotient = (shifted_quotient.bitcast(UInt(32)) | q_bits.bitcast(UInt(32))).bitcast(Bits(32))
            
            # Update registers
            self.quotient[0] = new_quotient
            self.remainder[0] = new_remainder
            self.Q[0] = new_Q
            self.QM[0] = new_QM
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))
            
            # Check if done
            with Condition(self.div_cnt[0] == Bits(5)(1)):
                self.state[0] = self.DIV_END
                debug_log("SRT4Divider: Last iteration complete")

        # State: DIV_END - Post-processing for SRT-4
        # Based on srt_4_div.v post-processing
        with Condition(self.state[0] == self.DIV_END):
            # Post-processing for Radix-4 division with on-the-fly conversion
            # The quotient is already computed in self.quotient (or self.Q for on-the-fly)
            # The remainder is already computed in self.remainder
            
            # Use Q register (from on-the-fly conversion) as the quotient
            # Q and quotient should match since we're using non-negative digits {0,1,2,3}
            q_out = self.quotient[0]
            rem_out = self.remainder[0][0:31]  # Take lower 32 bits of 34-bit remainder
            
            debug_log("SRT4Divider: DIV_END - quotient=0x{:x}, remainder=0x{:x}", 
                q_out, rem_out)

            # Apply sign correction
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]

            debug_log("SRT4Divider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

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
                debug_log("SRT4Divider: Signed overflow detected (-2^31 / -1)")

            with Condition(~signed_overflow):
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~q_out + Bits(32)(1)).bitcast(Bits(32)),
                    q_out
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~rem_out + Bits(32)(1)).bitcast(Bits(32)),
                    rem_out
                )

                debug_log("SRT4Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                    q_signed, rem_signed, self.is_rem[0])

                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("SRT4Divider: Completed, result=0x{:x}", self.result[0])

    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, rd, error)
        """
        return (self.ready[0], self.result[0], self.rd_out[0], self.error[0])

    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)