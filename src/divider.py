"""
SRT-4 (Sweeney-Robertson-Tocher) Divider Module for RV32IM Division Instructions

This module implements a true SRT-4 division algorithm that computes
2 quotient bits per clock cycle using a redundant digit set {-2, -1, 0, 1, 2}.

Architecture Overview:
=====================

SRT-4 division differs from radix-4 restoring division in several key ways:
1. Uses redundant quotient digits {-2, -1, 0, 1, 2} (signed-digit representation)
2. Employs a Quotient Digit Selection (QDS) function based on truncated partial
   remainder and divisor
3. Uses on-the-fly quotient conversion with Q and QM registers
4. Requires pre-normalization of the divisor

Key Benefits:
- More efficient quotient selection (simpler comparisons)
- Smaller hardware for QDS compared to comparing against 3*d
- Well-suited for hardware implementation

Timing:
- 1 cycle: Preprocessing (DIV_PRE) - convert to unsigned, normalize divisor
- 16 cycles: Iterative calculation (DIV_WORKING) - 2 bits per cycle
- 1 cycle: Post-processing (DIV_END) - sign correction, final quotient selection
- Total: ~18 cycles for normal division

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)

SRT-4 Algorithm:
================
1. Pre-normalization: Shift divisor d so leading 1 is at position 31
   - Track shift amount s
   - Shift dividend by the same amount
2. Initialize: w (partial remainder) = dividend, Q = 0, QM = -1
3. For i = 15 down to 0 (16 iterations):
   a. Select quotient digit q from {-2, -1, 0, 1, 2} based on truncated w and d
   b. Update partial remainder: w = 4*w - q*d
   c. Update Q and QM (on-the-fly conversion)
4. Post-processing:
   - If final w < 0, use QM, else use Q
   - Apply remainder correction if needed
   - Apply sign correction

Quotient Digit Selection (QDS):
- Based on the top bits of the shifted partial remainder
- For SRT-4 with maximally redundant digit set, the selection regions overlap
- This allows for simpler selection logic with more tolerance for estimation errors
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class SRT4Divider:
    """
    SRT-4 (Sweeney-Robertson-Tocher) division for 32-bit operands.

    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (convert to unsigned, normalize divisor)
    - 16 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (sign correction, final quotient)

    SRT-4 Key Features:
    - Uses redundant quotient digit set {-2, -1, 0, 1, 2}
    - Quotient Digit Selection (QDS) based on truncated partial remainder
    - On-the-fly quotient conversion using Q and QM registers
    - Pre-normalization of divisor for consistent QDS
    
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
        self.div_cnt = RegArray(Bits(5), 1, initializer=[0])  # Iteration counter

        # Internal working registers for SRT-4
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor (normalized)
        
        # Normalization shift amount (how many bits the divisor was shifted)
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])
        
        # Shifted partial remainder (35 bits: sign + 2 extra bits for 4*w computation)
        # Need extra bits because we compute 4*w - q*d where q can be -2 to +2
        self.shift_rem = RegArray(Bits(35), 1, initializer=[0])
        
        # On-the-fly quotient conversion registers
        # Q holds the quotient assuming next digit is 0 or positive
        # QM holds the quotient assuming next digit is negative (Q minus 1 in LSB position)
        self.Q = RegArray(Bits(32), 1, initializer=[0])
        self.QM = RegArray(Bits(32), 1, initializer=[0])
        
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

    def find_leading_one(self, value):
        """
        Find the position of the leading 1 bit in a 32-bit value.
        Returns a 6-bit shift amount (0-31, or 32 if value is 0).
        
        This is used for normalizing the divisor.
        """
        # Build a priority encoder using cascaded conditions
        # Check from MSB to LSB
        result = Bits(6)(32)  # Default: no leading 1 found
        
        # Check each bit position from 31 down to 0
        for i in range(31, -1, -1):
            bit_set = value[i:i] == Bits(1)(1)
            shift_amt = Bits(6)(31 - i)  # How much to shift left to put this bit at position 31
            result = bit_set.select(shift_amt, result)
        
        return result

    def quotient_select(self, w_truncated):
        """
        SRT-4 Quotient Digit Selection (QDS) function.
        
        This function selects a quotient digit from {-2, -1, 0, 1, 2}
        based on the truncated partial remainder.
        
        For SRT-4 with maximally redundant digit set (a=2, r=4):
        - The selection is based on comparing truncated w against thresholds
        - We use a simplified Robertson diagram approach
        
        Args:
            w_truncated: The top 6 bits of the shifted partial remainder (signed)
        
        Returns:
            q: Quotient digit encoded as 3-bit signed value
               000 = 0, 001 = 1, 010 = 2, 111 = -1, 110 = -2
        """
        # For SRT-4 with normalized divisor (1/2 <= d < 1):
        # The selection boundaries are approximately:
        # q = +2: w >= 3/2 * d  (roughly w >= 6 in fixed point)
        # q = +1: w >= 1/2 * d  (roughly w >= 2 in fixed point)
        # q =  0: -1/2 * d < w < 1/2 * d  (roughly -2 < w < 2)
        # q = -1: w <= -1/2 * d  (roughly w <= -2)
        # q = -2: w <= -3/2 * d  (roughly w <= -6)
        
        # w_truncated is the top bits of partial remainder in 2's complement
        # We interpret it as a signed 6-bit value
        
        # Selection thresholds (adjusted for our representation)
        # Using simple thresholds that work for normalized divisor 1/2 <= d < 1
        
        # Check if w_truncated is negative (sign bit)
        w_sign = w_truncated[5:5]
        
        # Threshold constants for QDS (in 6-bit 2's complement):
        # THRESHOLD_POS_6 = 6 (binary 000110) - boundary for q=+2
        # THRESHOLD_POS_2 = 2 (binary 000010) - boundary for q=+1
        # For negative values in 2's complement:
        # -2 = 111110 (0x3E)
        # -6 = 111010 (0x3A)
        # In 2's complement, more negative values have smaller unsigned representation
        THRESHOLD_POS_6 = Bits(6)(6)
        THRESHOLD_POS_2 = Bits(6)(2)
        THRESHOLD_NEG_2 = Bits(6)(0b111110)  # -2 in 6-bit 2's complement
        THRESHOLD_NEG_6 = Bits(6)(0b111010)  # -6 in 6-bit 2's complement
        
        # For positive values (sign bit = 0), check against positive thresholds
        # For negative values (sign bit = 1), check against negative thresholds
        ge_6 = (w_sign == Bits(1)(0)) & (w_truncated >= THRESHOLD_POS_6)
        ge_2 = (w_sign == Bits(1)(0)) & (w_truncated >= THRESHOLD_POS_2)
        
        # For negative values in 2's complement:
        # w <= -6 means w_truncated <= 111010 (more negative values have smaller binary)
        # w <= -2 means w_truncated <= 111110
        # -6 < w <= -2 means 111010 < w_truncated <= 111110
        is_negative = (w_sign == Bits(1)(1))
        # In 2's complement, w <= -6 means the binary value is <= 0b111010
        le_neg6 = is_negative & (w_truncated <= THRESHOLD_NEG_6)
        # -6 < w <= -2 (between -6 and -2, exclusive of -6)
        in_neg2_range = is_negative & (w_truncated > THRESHOLD_NEG_6) & (w_truncated <= THRESHOLD_NEG_2)
        
        # Select quotient digit (encoded as 3-bit: +2=010, +1=001, 0=000, -1=111, -2=110)
        q = ge_6.select(
            Bits(3)(0b010),  # q = +2
            ge_2.select(
                Bits(3)(0b001),  # q = +1
                le_neg6.select(
                    Bits(3)(0b110),  # q = -2
                    in_neg2_range.select(
                        Bits(3)(0b111),  # q = -1
                        Bits(3)(0b000)   # q = 0
                    )
                )
            )
        )
        
        return q

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

        # State: DIV_PRE - Preprocessing and normalization
        with Condition(self.state[0] == self.DIV_PRE):
            # SRT-4 requires normalized divisor (leading 1 at position 31)
            # Find leading 1 position in divisor
            shift_amt = self.find_leading_one(self.divisor_r[0])
            
            # Normalize divisor: shift left so leading 1 is at MSB
            # We use a barrel shifter approach
            divisor_val = self.divisor_r[0]
            
            # Build normalized divisor using cascaded shifts
            # Handle the special case where shift_amt = 0 (already normalized)
            norm_divisor = divisor_val
            for i in range(32):
                is_shift_i = (shift_amt == Bits(6)(i))
                # Left shift by i positions
                if i == 0:
                    shifted = divisor_val
                elif i == 31:
                    # Special case: left shift by 31 moves bit 0 (LSB) to bit 31 (MSB position)
                    # and fills lower 31 bits with zeros
                    shifted = concat(divisor_val[0:0], Bits(31)(0))
                else:
                    # Left shift by i: take lower (32-i) bits and pad with i zeros on the right
                    shifted = concat(divisor_val[0:31-i], Bits(i)(0))
                norm_divisor = is_shift_i.select(shifted, norm_divisor)
            
            self.divisor_r[0] = norm_divisor
            self.div_shift[0] = shift_amt
            
            # Initialize partial remainder with dividend (extended to 35 bits)
            # The dividend represents the initial partial remainder
            self.shift_rem[0] = concat(Bits(3)(0), self.dividend_r[0])
            
            # Initialize on-the-fly conversion registers
            # Q starts at 0, QM starts at -1 (all 1s)
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0xFFFFFFFF)
            
            # Initialize iteration counter (16 iterations for 32-bit / 2 bits per iteration)
            self.div_cnt[0] = Bits(5)(16)

            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING

            debug_log("SRT4Divider: Preprocessing complete, shift={}, starting 16 iterations", shift_amt)

        # State: DIV_WORKING - Iterative SRT-4 division
        with Condition(self.state[0] == self.DIV_WORKING):
            # Check if done (counter reaches 1, meaning this is the last iteration)
            with Condition(self.div_cnt[0] == Bits(5)(1)):
                self.state[0] = self.DIV_END
                debug_log("SRT4Divider: Iterations complete, entering post-processing")

            # SRT-4 algorithm:
            # 1. Select quotient digit based on truncated partial remainder
            # 2. Update partial remainder: w = 4*w - q*d
            # 3. Update Q and QM (on-the-fly conversion)

            # Step 1: Select quotient digit
            # Extract top 6 bits of partial remainder for QDS
            w_truncated = self.shift_rem[0][29:34]  # Top 6 bits
            q_digit = self.quotient_select(w_truncated)
            
            # Step 2: Compute new partial remainder
            # w_new = 4 * w - q * d
            # First, shift w left by 2 (multiply by 4)
            # Take lower 33 bits and shift left by 2, then truncate to 35 bits
            w_shifted = concat(self.shift_rem[0][0:32], Bits(2)(0))  # Take bits 0-32, shift left by 2
            
            # Compute q * d (where q is from {-2, -1, 0, 1, 2})
            # d is 32 bits, extend to 35 bits for arithmetic
            d_extended = concat(Bits(3)(0), self.divisor_r[0])
            d_2x = concat(Bits(2)(0), self.divisor_r[0], Bits(1)(0))  # 2*d (shifted left 1)
            
            # Decode q_digit and compute q * d
            # q encoding: 010=+2, 001=+1, 000=0, 111=-1, 110=-2
            is_q_pos2 = (q_digit == Bits(3)(0b010))
            is_q_pos1 = (q_digit == Bits(3)(0b001))
            is_q_zero = (q_digit == Bits(3)(0b000))
            is_q_neg1 = (q_digit == Bits(3)(0b111))
            is_q_neg2 = (q_digit == Bits(3)(0b110))
            
            # For positive q: subtract q*d
            # For negative q: add |q|*d (subtract negative)
            # w_new = 4*w - q*d
            
            # Compute adjustments
            qd_pos2 = d_2x  # +2 * d
            qd_pos1 = d_extended  # +1 * d
            qd_zero = Bits(35)(0)
            qd_neg1 = d_extended  # |-1| * d
            qd_neg2 = d_2x  # |-2| * d
            
            # Select q*d based on q_digit
            # For positive q, we subtract; for negative q, we add
            qd_value = is_q_pos2.select(
                qd_pos2,
                is_q_pos1.select(
                    qd_pos1,
                    is_q_neg2.select(
                        qd_neg2,
                        is_q_neg1.select(
                            qd_neg1,
                            qd_zero
                        )
                    )
                )
            )
            
            is_q_negative = is_q_neg1 | is_q_neg2
            
            # Compute w_new = 4*w - q*d
            # If q >= 0: w_new = w_shifted - qd_value
            # If q < 0: w_new = w_shifted + qd_value
            w_minus_qd = (w_shifted.bitcast(UInt(35)) - qd_value.bitcast(UInt(35))).bitcast(Bits(35))
            w_plus_qd = (w_shifted.bitcast(UInt(35)) + qd_value.bitcast(UInt(35))).bitcast(Bits(35))
            
            new_w = is_q_negative.select(w_plus_qd, w_minus_qd)
            
            # Step 3: On-the-fly quotient conversion
            # The on-the-fly algorithm maintains Q (quotient) and QM (Q - 1)
            # For each digit q in {-2, -1, 0, 1, 2}:
            #   if q >= 0: Q_new = 4*Q + q, QM_new = 4*Q + q - 1
            #   if q < 0:  Q_new = 4*QM + (4 + q), QM_new = 4*QM + (4 + q) - 1
            
            Q_shifted = concat(self.Q[0][0:29], Bits(2)(0))  # Q << 2
            QM_shifted = concat(self.QM[0][0:29], Bits(2)(0))  # QM << 2
            
            # Decode q value for on-the-fly conversion
            # q=+2: add 2 to 4*Q
            # q=+1: add 1 to 4*Q
            # q=0:  add 0 to 4*Q
            # q=-1: use 4*QM + 3
            # q=-2: use 4*QM + 2
            
            Q_add_2 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(2).bitcast(UInt(32))).bitcast(Bits(32))
            Q_add_1 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32))
            Q_add_0 = Q_shifted
            QM_add_3 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(3).bitcast(UInt(32))).bitcast(Bits(32))
            QM_add_2 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(2).bitcast(UInt(32))).bitcast(Bits(32))
            
            # New Q value
            new_Q = is_q_pos2.select(
                Q_add_2,
                is_q_pos1.select(
                    Q_add_1,
                    is_q_zero.select(
                        Q_add_0,
                        is_q_neg1.select(
                            QM_add_3,
                            QM_add_2  # q = -2
                        )
                    )
                )
            )
            
            # New QM = new_Q - 1
            new_QM = (new_Q.bitcast(UInt(32)) - Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32))

            # Update registers
            self.shift_rem[0] = new_w
            self.Q[0] = new_Q
            self.QM[0] = new_QM

            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            debug_log("SRT4Divider: DIV_END - Q=0x{:x}, QM=0x{:x}, shift_rem=0x{:x}",
                self.Q[0], self.QM[0], self.shift_rem[0])

            # Final quotient selection:
            # If final partial remainder is negative, use QM, else use Q
            final_rem_sign = self.shift_rem[0][34:34]
            
            # Select quotient based on remainder sign
            raw_quotient = final_rem_sign.select(self.QM[0], self.Q[0])
            
            # Adjust quotient for normalization shift
            # The quotient needs to be shifted right by the normalization amount
            # because we normalized the divisor, the quotient is too large by that factor
            shift_amt = self.div_shift[0]
            
            # Right shift the quotient by shift_amt
            adjusted_quotient = raw_quotient
            for i in range(32):
                is_shift_i = (shift_amt == Bits(6)(i))
                if i == 0:
                    shifted_q = raw_quotient
                elif i == 31:
                    # Special case: right shift by 31 keeps only the MSB at LSB position
                    shifted_q = concat(Bits(31)(0), raw_quotient[31:31])
                else:
                    # Right shift by i: take bits [i:31] and pad with zeros on left
                    shifted_q = concat(Bits(i)(0), raw_quotient[i:31])
                adjusted_quotient = is_shift_i.select(shifted_q, adjusted_quotient)
            
            # Compute the remainder
            # remainder = dividend - quotient * divisor
            # We need to use the original (non-normalized) divisor for this
            # The partial remainder in shift_rem is scaled, so we need to unscale
            
            # For the remainder, we compute: remainder = dividend - adjusted_quotient * original_divisor
            # Using the property that dividend = quotient * divisor + remainder
            
            # Get original divisor by right-shifting normalized divisor
            orig_divisor = self.divisor_r[0]
            for i in range(32):
                is_shift_i = (shift_amt == Bits(6)(i))
                if i == 0:
                    unshifted_d = self.divisor_r[0]
                elif i == 31:
                    # Special case: right shift by 31 keeps only the MSB at LSB position
                    unshifted_d = concat(Bits(31)(0), self.divisor_r[0][31:31])
                else:
                    unshifted_d = concat(Bits(i)(0), self.divisor_r[0][i:31])
                orig_divisor = is_shift_i.select(unshifted_d, orig_divisor)
            
            # Compute remainder = dividend - quotient * divisor
            # For simplicity, use: remainder = dividend mod divisor property
            # Since we're doing integer division, remainder = dividend - (quotient * divisor)
            product = (adjusted_quotient.bitcast(UInt(32)) * orig_divisor.bitcast(UInt(32))).bitcast(Bits(64))
            product_low = product[0:31]
            computed_remainder = (self.dividend_r[0].bitcast(UInt(32)) - product_low.bitcast(UInt(32))).bitcast(Bits(32))
            
            # Apply sign correction
            # For quotient: if signs differ, negate
            # For remainder: same sign as dividend
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]  # Dividend sign

            debug_log("SRT4Divider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

            # Check for signed overflow: (-2^31) / (-1)
            min_int = Bits(32)(0x80000000)
            neg_one = Bits(32)(0xFFFFFFFF)
            signed_overflow = (self.sign_r[0] == Bits(1)(1)) & \
                              (self.dividend_in[0] == min_int) & \
                              (self.divisor_in[0] == neg_one)

            with Condition(signed_overflow):
                # Handle signed overflow per RISC-V spec
                self.result[0] = self.is_rem[0].select(
                    Bits(32)(0),  # Remainder = 0
                    Bits(32)(0x80000000)  # Quotient = -2^31 (no change)
                )
                debug_log("SRT4Divider: Signed overflow detected (-2^31 / -1)")

            with Condition(~signed_overflow):
                # Normal result with sign correction
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~adjusted_quotient + Bits(32)(1)).bitcast(Bits(32)),
                    adjusted_quotient
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~computed_remainder + Bits(32)(1)).bitcast(Bits(32)),
                    computed_remainder
                )

                debug_log("SRT4Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                    q_signed, rem_signed, self.is_rem[0])

                # Select quotient or remainder
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