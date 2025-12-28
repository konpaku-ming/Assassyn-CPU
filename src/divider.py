"""
SRT-4 Divider Module for RV32IM Division Instructions

This module implements the SRT-4 divider algorithm in Python/Assassyn,
based on the reference Verilog implementation in SRT4/SRT4.v.
It provides a native interface compatible with the Assassyn CPU pipeline.

Architecture Overview:
=====================

The SRT-4 divider is a radix-4 division algorithm that computes 2 quotient bits
per clock cycle. It uses a quotient selection logic based on partial remainder
and normalized divisor to select quotient digits from {-2, -1, 0, 1, 2}.

Timing:
- 1 cycle: Preprocessing (DIV_PRE) - normalize divisor, find leading 1
- ~16 cycles: Iterative calculation (DIV_WORKING) - 32 bits / 2 bits per cycle
- 1 cycle: Post-processing (DIV_END) - sign correction and remainder adjustment
- Total: ~18 cycles for normal division

Special cases are handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)

FSM States:
- IDLE: Wait for valid signal
- DIV_PRE: Preprocessing
- DIV_WORKING: Iterative SRT-4 calculation
- DIV_END: Post-processing
- DIV_1: Fast path for divisor = 1
- DIV_ERROR: Error handling for divisor = 0
"""

from assassyn.frontend import *


class SRT4Divider:
    """
    Pure Python/Assassyn implementation of SRT-4 32-bit divider.
    
    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (alignment via find_1)
    - 16 cycles: Iterative calculation (2 bits per cycle using q_sel)
    - 1 cycle: Post-processing (sign correction)
    
    Pipeline Integration:
    - When a division instruction enters EX stage, the divider is started
    - The pipeline stalls (IF/ID/EX) until divider completes
    - Result is written back to register file through normal WB path
    
    Implementation Notes:
    - Implements SRT-4 algorithm: radix-4, quotient digit q ∈ {-2, -1, 0, 1, 2}
    - Uses quotient selection logic (q_sel) based on partial remainder and divisor
    - Handles signed/unsigned division and remainder operations
    - Detects and handles special cases (div-by-zero, signed overflow)
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

        # Output results
        self.result = RegArray(Bits(32), 1, initializer=[0])
        self.ready = RegArray(Bits(1), 1, initializer=[0])
        self.error = RegArray(Bits(1), 1, initializer=[0])  # Division by zero

        # SRT-4 state machine registers
        self.state = RegArray(Bits(3), 1, initializer=[0])  # FSM state
        self.div_cnt = RegArray(Bits(5), 1, initializer=[0])  # Iteration counter (16 iterations for 32-bit)

        # Internal working registers (similar to SRT4.v)
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor
        self.div_shift = RegArray(Bits(5), 1, initializer=[0])  # Alignment shift amount
        self.shift_rem = RegArray(Bits(65), 1, initializer=[0])  # Partial remainder (2*WID+1 = 65 bits)
        self.Q = RegArray(Bits(33), 1, initializer=[0])  # Quotient accumulator (WID+1 = 33 bits)
        self.QM = RegArray(Bits(33), 1, initializer=[0])  # Quotient-1 accumulator
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])  # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])  # Sign flag for result

        # Intermediate values for post-processing
        self.fin_q = RegArray(Bits(33), 1, initializer=[0])
        self.fin_rem = RegArray(Bits(33), 1, initializer=[0])

        # FSM states (matching SRT4.v)
        self.IDLE = Bits(3)(0)
        self.DIV_PRE = Bits(3)(1)
        self.DIV_WORKING = Bits(3)(2)
        self.DIV_END = Bits(3)(3)
        self.DIV_1 = Bits(3)(4)
        self.DIV_ERROR = Bits(3)(5)

    def is_busy(self):
        """Check if divider is currently processing"""
        return self.busy[0]

    def start_divide(self, dividend, divisor, is_signed, is_rem):
        """
        Start a division operation.

        Args:
            dividend: 32-bit dividend (rs1)
            divisor: 32-bit divisor (rs2)
            is_signed: 1 for signed (DIV/REM), 0 for unsigned (DIVU/REMU)
            is_rem: 1 to return remainder, 0 to return quotient
        """
        self.dividend_in[0] = dividend
        self.divisor_in[0] = divisor
        self.is_signed[0] = is_signed
        self.is_rem[0] = is_rem
        self.valid_in[0] = Bits(1)(1)
        self.busy[0] = Bits(1)(1)
        self.ready[0] = Bits(1)(0)
        self.error[0] = Bits(1)(0)

        log("Divider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
            dividend,
            divisor,
            is_signed)

    def find_leading_one(self, d):
        """
        Find position of leading 1 in divisor (implements find_1.v logic).
        Returns the value needed for normalization shift amount.

        This implements the same logic as find_1.v module:
        - For a divisor with MSB at position P, returns (30 - P)
        - This allows div_shift = pos_1 + 1 = 31 - P
        - After shifting by div_shift, the divisor's MSB will be at bit 31

        For example:
        - divisor = 2 = 0b10, MSB at position 1
        - Returns 30 - 1 = 29
        - div_shift = 29 + 1 = 30
        - 2 << 30 = 0x80000000 (MSB now at bit 31) ✓

        Args:
            d: 32-bit divisor

        Returns:
            Position value for normalization (30 - MSB_position)
        """
        # Find the MSB position first
        msb_pos = Bits(5)(0)

        # Check each bit from LSB to MSB, updating msb_pos when we find a 1
        # This creates a priority encoder where higher bits take precedence
        for i in range(0, 32):
            bit_set = (d[i:i] == Bits(1)(1))
            msb_pos = bit_set.select(Bits(5)(i), msb_pos)

        # Return 30 - MSB_position to match Verilog find_1 behavior
        # This is equivalent to (WID-2) - msb_pos for WID=32
        pos_1 = (Bits(5)(30).bitcast(UInt(5)) - msb_pos.bitcast(UInt(5))).bitcast(Bits(5))

        return pos_1

    def power_of_2(self, exponent, width):
        """
        Compute 2^exponent for a given exponent value.

        This function computes the power of 2 by iteratively selecting
        between the current result and result * power based on
        each bit of the exponent.

        The algorithm works by representing the exponent in binary:
        - If bit i of exponent is set, multiply result by 2^(2^i)
        - bit 0 -> multiply by 2^1 = 2
        - bit 1 -> multiply by 2^2 = 4
        - bit 2 -> multiply by 2^4 = 16
        - bit 3 -> multiply by 2^8 = 256
        - bit 4 -> multiply by 2^16 = 65536

        Args:
            exponent: The exponent value (as Bits type)
            width: The bit width of the result

        Returns:
            2^exponent as a Bits value of specified width
        """
        # Start with 2^0 = 1
        result = Bits(width)(1)

        # For each bit in the exponent, if the bit is set,
        # we multiply by the corresponding power of 2
        power = Bits(width)(2)  # Start with 2^(2^0) = 2^1 = 2

        # Process each bit of the exponent (assuming max 5 bits for shift amounts 0-31)
        for i in range(5):
            bit_is_set = exponent[i:i] == Bits(1)(1)
            result = bit_is_set.select(
                (result.bitcast(UInt(width)) * power.bitcast(UInt(width))).bitcast(Bits(width)),
                result
            )
            # Square the power for the next bit: 2 -> 4 -> 16 -> 256 -> 65536
            power = (power.bitcast(UInt(width)) * power.bitcast(UInt(width))).bitcast(Bits(width))

        return result

    def quotient_select(self, rem_high, d_high):
        """
        Quotient digit selection logic (implements q_sel.v).

        Based on the high bits of partial remainder and divisor, select
        the next quotient digit q ∈ {-2, -1, 0, 1, 2}.

        Args:
            rem_high: High 6 bits of partial remainder (bits [64:59] of shift_rem)
            d_high: High 4 bits of normalized divisor (bits [32:29] of divisor_r << div_shift)

        Returns:
            (q, neg): quotient digit (0, 1, 2) and sign flag
            If neg=1, q should be negated: actual q = -q
        """
        # Implementation of q_sel.v lookup table logic
        # This uses the same selection criteria as the Verilog version

        # Determine which lookup table to use based on d_high (4 bits)
        # Tables are numbered 8-15 (0b1000 to 0b1111)
        table_8 = (d_high == Bits(4)(0b1000))
        table_9 = (d_high == Bits(4)(0b1001))
        table_10 = (d_high == Bits(4)(0b1010))
        table_11 = (d_high == Bits(4)(0b1011))
        table_12 = (d_high == Bits(4)(0b1100))
        table_13 = (d_high == Bits(4)(0b1101))
        table_14 = (d_high == Bits(4)(0b1110))
        table_15 = (d_high == Bits(4)(0b1111))

        # Determine if quotient should be negative
        # Based on rem_high ranges for each table
        neg = (table_8 & ((rem_high >= Bits(6)(0b110100)) & (rem_high < Bits(6)(0b111110)))) | \
              (table_9 & ((rem_high >= Bits(6)(0b110010)) & (rem_high < Bits(6)(0b111101)))) | \
              (table_10 & ((rem_high >= Bits(6)(0b110001)) & (rem_high < Bits(6)(0b111101)))) | \
              (table_11 & ((rem_high >= Bits(6)(0b110000)) & (rem_high < Bits(6)(0b111101)))) | \
              (table_12 & ((rem_high >= Bits(6)(0b101110)) & (rem_high < Bits(6)(0b111100)))) | \
              (table_13 & ((rem_high >= Bits(6)(0b101101)) & (rem_high < Bits(6)(0b111100)))) | \
              (table_14 & ((rem_high >= Bits(6)(0b101100)) & (rem_high < Bits(6)(0b111100)))) | \
              (table_15 & ((rem_high >= Bits(6)(0b101010)) & (rem_high < Bits(6)(0b111100))))

        # Determine if quotient digit is 2
        q2 = (table_8 & (((rem_high >= Bits(6)(0b110100)) & (rem_high < Bits(6)(0b111010))) | \
                         ((rem_high >= Bits(6)(0b000110)) & (rem_high <= Bits(6)(0b001011))))) | \
             (table_9 & (((rem_high >= Bits(6)(0b110010)) & (rem_high < Bits(6)(0b111001))) | \
                         ((rem_high >= Bits(6)(0b000111)) & (rem_high <= Bits(6)(0b001101))))) | \
             (table_10 & (((rem_high >= Bits(6)(0b110001)) & (rem_high < Bits(6)(0b111000))) | \
                          ((rem_high >= Bits(6)(0b001000)) & (rem_high <= Bits(6)(0b001110))))) | \
             (table_11 & (((rem_high >= Bits(6)(0b110000)) & (rem_high < Bits(6)(0b110111))) | \
                          ((rem_high >= Bits(6)(0b001000)) & (rem_high <= Bits(6)(0b001111))))) | \
             (table_12 & (((rem_high >= Bits(6)(0b101110)) & (rem_high < Bits(6)(0b110110))) | \
                          ((rem_high >= Bits(6)(0b001001)) & (rem_high <= Bits(6)(0b010001))))) | \
             (table_13 & (((rem_high >= Bits(6)(0b101101)) & (rem_high < Bits(6)(0b110110))) | \
                          ((rem_high >= Bits(6)(0b001010)) & (rem_high <= Bits(6)(0b010010))))) | \
             (table_14 & (((rem_high >= Bits(6)(0b101100)) & (rem_high < Bits(6)(0b110101))) | \
                          ((rem_high >= Bits(6)(0b001010)) & (rem_high <= Bits(6)(0b010011))))) | \
             (table_15 & (((rem_high >= Bits(6)(0b101010)) & (rem_high < Bits(6)(0b110100))) | \
                          ((rem_high >= Bits(6)(0b001011)) & (rem_high <= Bits(6)(0b010101)))))

        # Determine if quotient digit is 0
        q0 = (table_8 & (((rem_high >= Bits(6)(0b111110)) & (rem_high <= Bits(6)(0b111111))) | \
                         ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000010))))) | \
             (table_9 & (((rem_high >= Bits(6)(0b111101)) & (rem_high <= Bits(6)(0b111111))) | \
                         ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000010))))) | \
             (table_10 & (((rem_high >= Bits(6)(0b111101)) & (rem_high <= Bits(6)(0b111111))) | \
                          ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000010))))) | \
             (table_11 & (((rem_high >= Bits(6)(0b111101)) & (rem_high <= Bits(6)(0b111111))) | \
                          ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000010))))) | \
             (table_12 & (((rem_high >= Bits(6)(0b111100)) & (rem_high <= Bits(6)(0b111111))) | \
                          ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000011))))) | \
             (table_13 & (((rem_high >= Bits(6)(0b111100)) & (rem_high <= Bits(6)(0b111111))) | \
                          ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000011))))) | \
             (table_14 & (((rem_high >= Bits(6)(0b111100)) & (rem_high <= Bits(6)(0b111111))) | \
                          ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000011))))) | \
             (table_15 & (((rem_high >= Bits(6)(0b111100)) & (rem_high <= Bits(6)(0b111111))) | \
                          ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000100)))))

        # Select quotient digit: q2 -> 2, q0 -> 0, otherwise -> 1
        q = q2.select(Bits(2)(0b10), q0.select(Bits(2)(0b00), Bits(2)(0b01)))

        return (q, neg)

    def tick(self):
        """
        Execute one cycle of the SRT-4 state machine.
        Should be called every clock cycle.

        This implements the main FSM from SRT4.v, including:
        - IDLE: Wait for valid signal, detect special cases
        - DIV_PRE: Preprocessing (convert to unsigned, find alignment)
        - DIV_WORKING: Iterative SRT-4 calculation (16 cycles)
        - DIV_END: Post-processing (sign correction)
        - DIV_1: Fast path for divisor = 1
        - DIV_ERROR: Handle division by zero
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
                    log("Divider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    log("Divider: Fast path (divisor=1)")

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

                    log("Divider: Starting normal division (DIV_PRE)")

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
            self.error[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("Divider: Completed with division by zero error")

        # State: DIV_1 - Fast path for divisor = 1
        with Condition(self.state[0] == self.DIV_1):
            # Fast path: quotient is dividend, remainder is 0
            self.result[0] = self.is_rem[0].select(
                Bits(32)(0),  # Remainder = 0
                self.dividend_in[0]  # Quotient = dividend
            )
            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("Divider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing
        with Condition(self.state[0] == self.DIV_PRE):
            # Find leading 1 position in divisor for normalization
            # This is similar to find_1.v module
            pos_1 = self.find_leading_one(self.divisor_r[0])
            self.div_shift[0] = pos_1 + Bits(5)(1)

            # Initialize partial remainder (left-shift dividend)
            # rem = {33'b0, dividend_r} << div_shift
            # For simplicity in simulation, we'll prepare it in next state

            # Initialize iteration counter (WID/2 = 32/2 = 16 iterations)
            # Counter counts down from 16 to 1, checking for 0 after decrement
            self.div_cnt[0] = Bits(5)(16)

            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING

            # Initialize shift_rem: {33'b0, dividend_r} << (pos_1 + 1)
            # This is a 65-bit value
            dividend_extended = concat(Bits(33)(0), self.dividend_r[0])
            # Shift left by div_shift amount using multiplication by power of 2
            # For hardware, this would be a barrel shifter
            # For simulation, we replace shift with multiplication
            shift_amount = (pos_1 + Bits(5)(1))[0:4].bitcast(UInt(5))
            # Replace left shift with multiplication: x << n = x * (2^n)
            power = self.power_of_2(shift_amount.bitcast(Bits(5)), 65)
            dividend_shifted = (dividend_extended.bitcast(UInt(65)) * power.bitcast(UInt(65))).bitcast(Bits(65))
            self.shift_rem[0] = dividend_shifted

            log("Divider: Preprocessing complete, shift={}, starting iterations", pos_1 + Bits(5)(1))

        # State: DIV_WORKING - Iterative SRT-4 calculation
        with Condition(self.state[0] == self.DIV_WORKING):
            # Extract high bits for quotient selection
            rem_high = self.shift_rem[0][59:64]  # Top 6 bits (bits 59-64)

            # Get high 4 bits of shifted divisor
            # shift_divisor = divisor_r << div_shift (33-bit with zero extension)
            shift_amount = self.div_shift[0][0:4].bitcast(UInt(5))
            # Replace left shift with multiplication: x << n = x * (2^n)
            power = self.power_of_2(shift_amount.bitcast(Bits(5)), 32)
            divisor_shifted = (self.divisor_r[0].bitcast(UInt(32)) * power.bitcast(UInt(32))).bitcast(Bits(32))
            # Zero-extend to 33 bits: {1'b0, divisor_shifted[31:0]}
            shift_divisor = concat(Bits(1)(0), divisor_shifted)
            d_high = shift_divisor[28:31]  # Top 4 bits (Verilog [31:28] of 33-bit value)

            # Select quotient digit
            (q, neg) = self.quotient_select(rem_high, d_high)

            # Compute multiples of shift_divisor
            shift_divisor_n = (~shift_divisor + Bits(33)(1)).bitcast(Bits(33))  # -divisor
            shift_divisor_X2 = (shift_divisor.bitcast(UInt(33)) + shift_divisor.bitcast(UInt(33))).bitcast(
                Bits(33))  # 2*divisor
            shift_divisor_X2n = (~shift_divisor_X2 + Bits(33)(1)).bitcast(Bits(33))  # -2*divisor

            # Update partial remainder based on q and neg
            # new_rem = (old_rem << 2) - q * divisor
            # Following SRT4.v logic: {shift_rem[62:30] + value, shift_rem[29:0], 2'b0}
            # Each case directly computes and assigns the new shift_rem in ONE expression
            # shift_rem is 65 bits: [64:0]
            # High part: [30:62] = 33 bits (Verilog [62:30]), Low part: [0:29] = 30 bits, Plus 2'b0 = 2 bits

            # Perform operation and assignment based on q and neg
            # neg=0: q=0,1,2 -> subtract 0, divisor, 2*divisor
            # neg=1: q=0,1,2 -> add 0, divisor, 2*divisor (subtract negative)
            with Condition(neg == Bits(1)(0)):
                # Positive quotient digit
                with Condition(q == Bits(2)(0b00)):
                    # q=0, neg=0: add 0
                    self.shift_rem[0] = concat(self.shift_rem[0][30:62], self.shift_rem[0][0:29], Bits(2)(0))
                with Condition(q == Bits(2)(0b01)):
                    # q=1, neg=0: subtract divisor
                    new_rem_high = (
                                self.shift_rem[0][30:62].bitcast(UInt(33)) + shift_divisor_n.bitcast(UInt(33))).bitcast(
                        Bits(33))
                    self.shift_rem[0] = concat(new_rem_high, self.shift_rem[0][0:29], Bits(2)(0))
                with Condition(q == Bits(2)(0b10)):
                    # q=2, neg=0: subtract 2*divisor
                    new_rem_high = (self.shift_rem[0][30:62].bitcast(UInt(33)) + shift_divisor_X2n.bitcast(
                        UInt(33))).bitcast(Bits(33))
                    self.shift_rem[0] = concat(new_rem_high, self.shift_rem[0][0:29], Bits(2)(0))
            with Condition(neg != Bits(1)(0)):
                # Negative quotient digit (add instead of subtract)
                with Condition(q == Bits(2)(0b00)):
                    # q=0, neg=1: add 0
                    self.shift_rem[0] = concat(self.shift_rem[0][30:62], self.shift_rem[0][0:29], Bits(2)(0))
                with Condition(q == Bits(2)(0b01)):
                    # q=1, neg=1: add divisor
                    new_rem_high = (
                                self.shift_rem[0][30:62].bitcast(UInt(33)) + shift_divisor.bitcast(UInt(33))).bitcast(
                        Bits(33))
                    self.shift_rem[0] = concat(new_rem_high, self.shift_rem[0][0:29], Bits(2)(0))
                with Condition(q == Bits(2)(0b10)):
                    # q=2, neg=1: add 2*divisor
                    new_rem_high = (self.shift_rem[0][30:62].bitcast(UInt(33)) + shift_divisor_X2.bitcast(
                        UInt(33))).bitcast(Bits(33))
                    self.shift_rem[0] = concat(new_rem_high, self.shift_rem[0][0:29], Bits(2)(0))

            # Update Q and QM accumulators
            # Q accumulator update based on sign of quotient digit
            # For 33-bit Q, the shift operation Q << 2 | q becomes {Q[30:0], q}
            with Condition(neg == Bits(1)(0)):
                # Positive quotient: Q = (Q << 2) | q
                # {Q[30:0], q} = 31 bits + 2 bits = 33 bits
                self.Q[0] = concat(self.Q[0][0:30], q)
            with Condition(neg != Bits(1)(0)):
                # Negative quotient: Q = (QM << 2) + (4 - q)
                # This requires handling the carry when q=0
                with Condition(q == Bits(2)(0)):
                    # q=0: (QM << 2) + 4 = (QM + 1) << 2
                    # This identity avoids explicit carry handling:
                    #   (X + 1) * 4 = X * 4 + 4
                    # Implementation: add 1 to QM, then shift left 2 (via concat)
                    qm_plus_one = (self.QM[0].bitcast(UInt(33)) + Bits(33)(1)).bitcast(Bits(33))
                    # {(QM+1)[30:0], 2'b00} = 31 bits + 2 bits = 33 bits
                    self.Q[0] = concat(qm_plus_one[0:30], Bits(2)(0b00))
                with Condition(q != Bits(2)(0)):
                    # q=1 or q=2: no carry needed
                    # Bottom 2 bits = (4 - q)
                    #   q=1: 4-1=3=0b11
                    #   q=2: 4-2=2=0b10
                    # Can compute as (~q + 1) & 0b11 for q in {1,2}:
                    #   q=1 (0b01): ~0b01 + 1 = 0b10 + 1 = 0b11 ✓
                    #   q=2 (0b10): ~0b10 + 1 = 0b01 + 1 = 0b10 ✓
                    four_minus_q = ((~q).bitcast(UInt(2)) + Bits(2)(1)).bitcast(Bits(2))
                    # {QM[30:0], (4-q)} = 31 bits + 2 bits = 33 bits
                    self.Q[0] = concat(self.QM[0][0:30], four_minus_q)

            # QM accumulator: QM = Q - 1
            # When neg=0 and q!=0: QM = (Q << 2) | (q-1)
            # Otherwise: QM = (QM << 2) | (~q & 0b11)
            with Condition((neg == Bits(1)(0)) & (q != Bits(2)(0))):
                # Positive and non-zero: QM gets Q's shifted value with q-1
                q_minus_1 = (q.bitcast(UInt(2)) - Bits(2)(1)).bitcast(Bits(2))
                # {Q[30:0], (q-1)} = 31 bits + 2 bits = 33 bits
                self.QM[0] = concat(self.Q[0][0:30], q_minus_1)
            with Condition((neg != Bits(1)(0)) | (q == Bits(2)(0))):
                # QM gets shifted with complement of q
                # {QM[30:0], ~q} = 31 bits + 2 bits = 33 bits
                self.QM[0] = concat(self.QM[0][0:30], ~q)

            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))

            # Check if done (counter reaches 1, meaning this is the last iteration)
            # Note: In hardware, the read of div_cnt[0] gets the OLD value (before decrement)
            # So we check for 1, not 0, to transition AFTER the 16th iteration
            with Condition(self.div_cnt[0] == Bits(5)(1)):
                self.state[0] = self.DIV_END
                log("Divider: Iterations complete, entering post-processing")

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            log("Divider: DIV_END - Q=0x{:x}, QM=0x{:x}, shift_rem[32:64]=0x{:x}",
                self.Q[0], self.QM[0], self.shift_rem[0][32:64])

            # Adjust remainder if negative
            rem_is_negative = self.shift_rem[0][64:64]  # MSB of remainder (bit 64)

            # Get shifted divisor for adjustment
            shift_amount = self.div_shift[0][0:4].bitcast(UInt(5))
            # Replace left shift with multiplication: x << n = x * (2^n)
            power = self.power_of_2(shift_amount.bitcast(Bits(5)), 32)
            divisor_shifted = (self.divisor_r[0].bitcast(UInt(32)) * power.bitcast(UInt(32))).bitcast(Bits(32))
            # Zero-extend to 33 bits: {1'b0, divisor_shifted[31:0]}
            shift_divisor = concat(Bits(1)(0), divisor_shifted)

            with Condition(rem_is_negative == Bits(1)(1)):
                # Remainder is negative, need to adjust
                adjusted_rem = (self.shift_rem[0][32:64].bitcast(UInt(33)) + shift_divisor.bitcast(UInt(33))).bitcast(
                    Bits(33))
                self.fin_rem[0] = adjusted_rem
                self.fin_q[0] = (self.Q[0].bitcast(UInt(33)) - Bits(33)(1)).bitcast(Bits(33))
                log("Divider: Remainder was negative, adjusted fin_q=0x{:x}", self.fin_q[0])
            with Condition(rem_is_negative != Bits(1)(1)):
                self.fin_rem[0] = self.shift_rem[0][32:64]
                self.fin_q[0] = self.Q[0]
                log("Divider: Remainder was positive, fin_q=0x{:x}", self.fin_q[0])

            # Right-shift remainder back
            # Shift the Bits value directly, not after converting to UInt
            # Convert shift amount to UInt for the shift operation
            fin_rem_shifted = self.fin_rem[0] >> shift_amount

            # Apply sign correction
            # For quotient: if signs differ, negate
            # For remainder: same sign as dividend
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]  # Dividend sign

            log("Divider: div_sign=0x{:x}, q_needs_neg={}, fin_q[0:31]=0x{:x}, "
                "fin_rem_shifted[0:31]=0x{:x}",
                self.div_sign[0], q_needs_neg, self.fin_q[0][0:31], fin_rem_shifted[0:31])

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
                log("Divider: Signed overflow detected (-2^31 / -1)")
            with Condition(~signed_overflow):
                # Normal result with sign correction
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~self.fin_q[0][0:31] + Bits(32)(1)).bitcast(Bits(32)),
                    self.fin_q[0][0:31]
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~fin_rem_shifted[0:31] + Bits(32)(1)).bitcast(Bits(32)),
                    fin_rem_shifted[0:31]
                )

                log("Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                    q_signed, rem_signed, self.is_rem[0])

                # Select quotient or remainder
                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("Divider: Completed, result=0x{:x}", self.result[0])

        # Clear Q and QM when not in DIV_WORKING state (matches Verilog behavior)
        # This ensures Q and QM are reset between divisions
        with Condition(self.state[0] != self.DIV_WORKING):
            self.Q[0] = Bits(33)(0)
            self.QM[0] = Bits(33)(0)

    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, error)
        """
        return (self.ready[0], self.result[0], self.error[0])

    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)