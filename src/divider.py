"""
SRT-4 Divider Module for RV32IM Division Instructions

This module implements the SRT-4 (Sweeney-Robertson-Tocher) division algorithm
that computes 2 quotient bits per clock cycle using a redundant digit set.

Architecture Overview:
=====================

SRT-4 division uses a redundant quotient digit set {-2, -1, 0, +1, +2}, which allows
for simpler hardware compared to non-redundant radix-4:
1. Overlapping selection ranges allow imprecise (truncated) comparison
2. Partial remainder can be negative (signed representation)
3. No need to compute 3*divisor (only 1*d and 2*d)

Key Algorithm (based on Verilog reference implementation):
1. Pre-processing: Normalize divisor to have MSB in position 31 (d ∈ [1/2, 1))
2. Shift dividend accordingly for correct alignment
3. For each iteration:
   a. Look up quotient digit q from {-2, -1, 0, +1, +2} using QDS table
   b. Update partial remainder: w_next = (w - q*d) << 2
   c. Update Q and QM using on-the-fly conversion
4. Post-processing: Fix negative remainder, denormalize result

Quotient Digit Selection (QDS):
- dividend_index: 7-bit signed value from partial remainder bits [35:29]
- divisor_index: 4-bit value from normalized divisor bits [32:29]
- Output: q_table ∈ {00=0, 01=±1, 10=±2}, sign determined by dividend_index sign

On-the-fly conversion for quotient digits {-2, -1, 0, +1, +2}:
- q=+2 (010): Q = Q<<2|10, QM = Q<<2|01
- q=+1 (001): Q = Q<<2|01, QM = Q<<2|00
- q=0  (000): Q = Q<<2|00, QM = QM<<2|11
- q=-1 (101): Q = QM<<2|11, QM = QM<<2|10
- q=-2 (110): Q = QM<<2|10, QM = QM<<2|01

Timing:
- 1 cycle: Preprocessing (DIV_PRE) - convert to unsigned, normalize, detect special cases
- Variable cycles: Iterative calculation (DIV_WORKING) - 2 bits per cycle
- 1 cycle: Post-processing (DIV_END) - sign correction, denormalize remainder
- Total: Varies based on divisor leading zeros (1-17 iterations)

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class SRT4Divider:
    """
    SRT-4 division for 32-bit operands with redundant quotient digits.

    The divider is a multi-cycle functional unit that takes variable cycles based on
    divisor normalization:
    - 1 cycle: Preprocessing (convert to unsigned, normalize, detect special cases)
    - 1-17 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (sign correction, denormalize remainder)

    Key features:
    - Uses redundant digit set {-2, -1, 0, +1, +2}
    - Uses on-the-fly conversion for quotient accumulation
    - Divisor normalization for correct quotient selection
    - QDS table lookup based on truncated partial remainder and normalized divisor

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

        # Internal working registers
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor
        
        # Partial remainder (w_reg): 36 bits signed for SRT-4
        # Format: [35:0] where bits [35:29] are used for QDS lookup
        self.w_reg = RegArray(Bits(36), 1, initializer=[0])
        
        # Compatibility alias for shift_rem (points to w_reg conceptually)
        self.shift_rem = RegArray(Bits(35), 1, initializer=[0])
        
        # Normalized divisor: 36 bits (padded for computation)
        self.divisor_norm = RegArray(Bits(36), 1, initializer=[0])
        
        # Quotient accumulator (for compatibility)
        self.quotient = RegArray(Bits(32), 1, initializer=[0])
        
        # Partial remainder for compatibility (alias to lower 34 bits of w_reg)
        self.remainder = RegArray(Bits(34), 1, initializer=[0])
        
        # On-the-fly conversion registers
        self.Q = RegArray(Bits(32), 1, initializer=[0])
        self.QM = RegArray(Bits(32), 1, initializer=[0])
        
        # Pre-processing outputs
        self.iterations = RegArray(Bits(5), 1, initializer=[0])  # Number of iterations needed
        self.recovery = RegArray(Bits(6), 1, initializer=[0])    # Shift amount for remainder recovery
        
        # Normalization shift amount (kept for compatibility)
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])
        
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
    
    def qds_table(self, dividend_index, divisor_index):
        """
        SRT-4 Quotient Digit Selection Table.
        
        Based on the Verilog radix4_table.v implementation.
        
        Args:
            dividend_index: 7-bit signed value (bits [35:29] of partial remainder)
            divisor_index: 4-bit value (bits [32:29] of normalized divisor, always 1xxx)
            
        Returns:
            q_table: 2-bit value indicating quotient magnitude
                - 00: q = 0
                - 01: q = ±1
                - 10: q = ±2
            The sign is determined by dividend_index[6] (sign bit)
        """
        # Compare thresholds for each divisor index value
        # divisor_index is always 1xxx (8-15) after normalization
        
        # Default result
        q_table = Bits(2)(0)
        
        # Helper: signed comparison using 7-bit signed interpretation
        # dividend_index is already signed (7-bit 2's complement)
        
        # For d=1.000 (divisor_index=8): thresholds are 12, 4, -4, -13
        d_1000 = (divisor_index == Bits(4)(8))
        d_1000_q2 = d_1000 & (dividend_index >= Bits(7)(12))
        d_1000_q1 = d_1000 & (dividend_index >= Bits(7)(4)) & (dividend_index < Bits(7)(12))
        d_1000_q0 = d_1000 & (dividend_index >= Bits(7)(0b1111100)) & (dividend_index < Bits(7)(4))  # >= -4
        d_1000_qn1 = d_1000 & (dividend_index >= Bits(7)(0b1110011)) & (dividend_index < Bits(7)(0b1111100))  # >= -13, < -4
        d_1000_qn2 = d_1000 & (dividend_index < Bits(7)(0b1110011))  # < -13
        
        # For d=1.001 (divisor_index=9): thresholds are 14, 4, -6, -15
        d_1001 = (divisor_index == Bits(4)(9))
        d_1001_q2 = d_1001 & (dividend_index >= Bits(7)(14))
        d_1001_q1 = d_1001 & (dividend_index >= Bits(7)(4)) & (dividend_index < Bits(7)(14))
        d_1001_q0 = d_1001 & (dividend_index >= Bits(7)(0b1111010)) & (dividend_index < Bits(7)(4))  # >= -6
        d_1001_qn1 = d_1001 & (dividend_index >= Bits(7)(0b1110001)) & (dividend_index < Bits(7)(0b1111010))  # >= -15, < -6
        d_1001_qn2 = d_1001 & (dividend_index < Bits(7)(0b1110001))  # < -15
        
        # For d=1.010 (divisor_index=10): thresholds are 15, 4, -6, -16
        d_1010 = (divisor_index == Bits(4)(10))
        d_1010_q2 = d_1010 & (dividend_index >= Bits(7)(15))
        d_1010_q1 = d_1010 & (dividend_index >= Bits(7)(4)) & (dividend_index < Bits(7)(15))
        d_1010_q0 = d_1010 & (dividend_index >= Bits(7)(0b1111010)) & (dividend_index < Bits(7)(4))  # >= -6
        d_1010_qn1 = d_1010 & (dividend_index >= Bits(7)(0b1110000)) & (dividend_index < Bits(7)(0b1111010))  # >= -16, < -6
        d_1010_qn2 = d_1010 & (dividend_index < Bits(7)(0b1110000))  # < -16
        
        # For d=1.011 (divisor_index=11): thresholds are 16, 4, -6, -18
        d_1011 = (divisor_index == Bits(4)(11))
        d_1011_q2 = d_1011 & (dividend_index >= Bits(7)(16))
        d_1011_q1 = d_1011 & (dividend_index >= Bits(7)(4)) & (dividend_index < Bits(7)(16))
        d_1011_q0 = d_1011 & (dividend_index >= Bits(7)(0b1111010)) & (dividend_index < Bits(7)(4))  # >= -6
        d_1011_qn1 = d_1011 & (dividend_index >= Bits(7)(0b1101110)) & (dividend_index < Bits(7)(0b1111010))  # >= -18, < -6
        d_1011_qn2 = d_1011 & (dividend_index < Bits(7)(0b1101110))  # < -18
        
        # For d=1.100 (divisor_index=12): thresholds are 18, 6, -8, -20
        d_1100 = (divisor_index == Bits(4)(12))
        d_1100_q2 = d_1100 & (dividend_index >= Bits(7)(18))
        d_1100_q1 = d_1100 & (dividend_index >= Bits(7)(6)) & (dividend_index < Bits(7)(18))
        d_1100_q0 = d_1100 & (dividend_index >= Bits(7)(0b1111000)) & (dividend_index < Bits(7)(6))  # >= -8
        d_1100_qn1 = d_1100 & (dividend_index >= Bits(7)(0b1101100)) & (dividend_index < Bits(7)(0b1111000))  # >= -20, < -8
        d_1100_qn2 = d_1100 & (dividend_index < Bits(7)(0b1101100))  # < -20
        
        # For d=1.101 (divisor_index=13): thresholds are 20, 6, -8, -20
        d_1101 = (divisor_index == Bits(4)(13))
        d_1101_q2 = d_1101 & (dividend_index >= Bits(7)(20))
        d_1101_q1 = d_1101 & (dividend_index >= Bits(7)(6)) & (dividend_index < Bits(7)(20))
        d_1101_q0 = d_1101 & (dividend_index >= Bits(7)(0b1111000)) & (dividend_index < Bits(7)(6))  # >= -8
        d_1101_qn1 = d_1101 & (dividend_index >= Bits(7)(0b1101100)) & (dividend_index < Bits(7)(0b1111000))  # >= -20, < -8
        d_1101_qn2 = d_1101 & (dividend_index < Bits(7)(0b1101100))  # < -20
        
        # For d=1.110 (divisor_index=14): thresholds are 20, 8, -8, -22
        d_1110 = (divisor_index == Bits(4)(14))
        d_1110_q2 = d_1110 & (dividend_index >= Bits(7)(20))
        d_1110_q1 = d_1110 & (dividend_index >= Bits(7)(8)) & (dividend_index < Bits(7)(20))
        d_1110_q0 = d_1110 & (dividend_index >= Bits(7)(0b1111000)) & (dividend_index < Bits(7)(8))  # >= -8
        d_1110_qn1 = d_1110 & (dividend_index >= Bits(7)(0b1101010)) & (dividend_index < Bits(7)(0b1111000))  # >= -22, < -8
        d_1110_qn2 = d_1110 & (dividend_index < Bits(7)(0b1101010))  # < -22
        
        # For d=1.111 (divisor_index=15): thresholds are 24, 8, -8, -24
        d_1111 = (divisor_index == Bits(4)(15))
        d_1111_q2 = d_1111 & (dividend_index >= Bits(7)(24))
        d_1111_q1 = d_1111 & (dividend_index >= Bits(7)(8)) & (dividend_index < Bits(7)(24))
        d_1111_q0 = d_1111 & (dividend_index >= Bits(7)(0b1111000)) & (dividend_index < Bits(7)(8))  # >= -8
        d_1111_qn1 = d_1111 & (dividend_index >= Bits(7)(0b1101000)) & (dividend_index < Bits(7)(0b1111000))  # >= -24, < -8
        d_1111_qn2 = d_1111 & (dividend_index < Bits(7)(0b1101000))  # < -24
        
        # Combine all q=2 cases
        q_2 = d_1000_q2 | d_1001_q2 | d_1010_q2 | d_1011_q2 | d_1100_q2 | d_1101_q2 | d_1110_q2 | d_1111_q2
        
        # Combine all q=1 cases
        q_1 = d_1000_q1 | d_1001_q1 | d_1010_q1 | d_1011_q1 | d_1100_q1 | d_1101_q1 | d_1110_q1 | d_1111_q1
        
        # Combine all q=-1 cases
        q_n1 = d_1000_qn1 | d_1001_qn1 | d_1010_qn1 | d_1011_qn1 | d_1100_qn1 | d_1101_qn1 | d_1110_qn1 | d_1111_qn1
        
        # Combine all q=-2 cases
        q_n2 = d_1000_qn2 | d_1001_qn2 | d_1010_qn2 | d_1011_qn2 | d_1100_qn2 | d_1101_qn2 | d_1110_qn2 | d_1111_qn2
        
        # Output: 2-bit magnitude
        q_table = (q_2 | q_n2).select(
            Bits(2)(0b10),
            (q_1 | q_n1).select(
                Bits(2)(0b01),
                Bits(2)(0b00)
            )
        )
        
        return q_table
    
    def pre_process(self, divisor, dividend):
        """
        Pre-processing for SRT-4 division.
        
        Normalizes the divisor so that its MSB is in bit 31 position.
        Also computes the number of iterations needed and the recovery shift.
        
        Based on the Verilog pre_processing.v implementation.
        
        Args:
            divisor: 32-bit unsigned divisor
            dividend: 32-bit unsigned dividend
            
        Returns:
            (divisor_star, dividend_star, iterations, recovery)
            - divisor_star: 35-bit normalized divisor
            - dividend_star: 38-bit normalized dividend
            - iterations: number of SRT iterations needed
            - recovery: shift amount for remainder recovery
        """
        # Find leading one position in divisor
        lz = Bits(6)(0)  # Leading zeros count
        for i in range(31, -1, -1):
            bit_set = divisor[i:i] == Bits(1)(1)
            lz = bit_set.select(Bits(6)(31 - i), lz)
        
        # Default values (for divisor = 0)
        divisor_star = Bits(35)(0)
        dividend_star = Bits(38)(0)
        iterations = Bits(5)(0)
        recovery = Bits(6)(0)
        
        # Case: divisor bit 31 set (divisor >= 0x80000000)
        d_31 = divisor[31:31] == Bits(1)(1)
        divisor_star = d_31.select(concat(Bits(3)(0), divisor), divisor_star)
        dividend_star = d_31.select(concat(Bits(5)(0), dividend, Bits(1)(0)), dividend_star)
        iterations = d_31.select(Bits(5)(1), iterations)
        recovery = d_31.select(Bits(6)(32), recovery)
        
        # Case: divisor bit 30 set
        d_30 = ~d_31 & (divisor[30:30] == Bits(1)(1))
        divisor_star = d_30.select(concat(Bits(3)(0), divisor[0:30], Bits(1)(0)), divisor_star)
        dividend_star = d_30.select(concat(Bits(6)(0), dividend), dividend_star)
        iterations = d_30.select(Bits(5)(2), iterations)
        recovery = d_30.select(Bits(6)(31), recovery)
        
        # Case: divisor bit 29 set
        d_29 = ~d_31 & ~d_30 & (divisor[29:29] == Bits(1)(1))
        divisor_star = d_29.select(concat(Bits(3)(0), divisor[0:29], Bits(2)(0)), divisor_star)
        dividend_star = d_29.select(concat(Bits(5)(0), dividend, Bits(1)(0)), dividend_star)
        iterations = d_29.select(Bits(5)(2), iterations)
        recovery = d_29.select(Bits(6)(30), recovery)
        
        # Case: divisor bit 28 set
        d_28 = ~d_31 & ~d_30 & ~d_29 & (divisor[28:28] == Bits(1)(1))
        divisor_star = d_28.select(concat(Bits(3)(0), divisor[0:28], Bits(3)(0)), divisor_star)
        dividend_star = d_28.select(concat(Bits(6)(0), dividend), dividend_star)
        iterations = d_28.select(Bits(5)(3), iterations)
        recovery = d_28.select(Bits(6)(29), recovery)
        
        # Continue for remaining bit positions...
        # For brevity, we'll use a loop-like pattern with nested selects
        
        # Case: divisor bit 27 set
        d_27 = ~d_31 & ~d_30 & ~d_29 & ~d_28 & (divisor[27:27] == Bits(1)(1))
        divisor_star = d_27.select(concat(Bits(3)(0), divisor[0:27], Bits(4)(0)), divisor_star)
        dividend_star = d_27.select(concat(Bits(5)(0), dividend, Bits(1)(0)), dividend_star)
        iterations = d_27.select(Bits(5)(3), iterations)
        recovery = d_27.select(Bits(6)(28), recovery)
        
        # Case: divisor bit 26 set
        d_26 = ~d_31 & ~d_30 & ~d_29 & ~d_28 & ~d_27 & (divisor[26:26] == Bits(1)(1))
        divisor_star = d_26.select(concat(Bits(3)(0), divisor[0:26], Bits(5)(0)), divisor_star)
        dividend_star = d_26.select(concat(Bits(6)(0), dividend), dividend_star)
        iterations = d_26.select(Bits(5)(4), iterations)
        recovery = d_26.select(Bits(6)(27), recovery)
        
        # Case: divisor bit 25 set
        d_25 = ~d_31 & ~d_30 & ~d_29 & ~d_28 & ~d_27 & ~d_26 & (divisor[25:25] == Bits(1)(1))
        divisor_star = d_25.select(concat(Bits(3)(0), divisor[0:25], Bits(6)(0)), divisor_star)
        dividend_star = d_25.select(concat(Bits(5)(0), dividend, Bits(1)(0)), dividend_star)
        iterations = d_25.select(Bits(5)(4), iterations)
        recovery = d_25.select(Bits(6)(26), recovery)
        
        # Case: divisor bit 24 set
        d_24 = ~d_31 & ~d_30 & ~d_29 & ~d_28 & ~d_27 & ~d_26 & ~d_25 & (divisor[24:24] == Bits(1)(1))
        divisor_star = d_24.select(concat(Bits(3)(0), divisor[0:24], Bits(7)(0)), divisor_star)
        dividend_star = d_24.select(concat(Bits(6)(0), dividend), dividend_star)
        iterations = d_24.select(Bits(5)(5), iterations)
        recovery = d_24.select(Bits(6)(25), recovery)
        
        # Case: divisor bit 23 set
        d_23 = ~d_31 & ~d_30 & ~d_29 & ~d_28 & ~d_27 & ~d_26 & ~d_25 & ~d_24 & (divisor[23:23] == Bits(1)(1))
        divisor_star = d_23.select(concat(Bits(3)(0), divisor[0:23], Bits(8)(0)), divisor_star)
        dividend_star = d_23.select(concat(Bits(5)(0), dividend, Bits(1)(0)), dividend_star)
        iterations = d_23.select(Bits(5)(5), iterations)
        recovery = d_23.select(Bits(6)(24), recovery)
        
        # For simplicity, handle remaining cases with a simpler approach
        # using the leading zero count we already computed
        
        # Compute shift amount for normalization
        shift_amt = lz
        
        # Handle cases for bits 22 down to 0 using shift
        d_low = ~d_31 & ~d_30 & ~d_29 & ~d_28 & ~d_27 & ~d_26 & ~d_25 & ~d_24 & ~d_23
        
        # For lower bits, we use the shift amount directly
        # iterations = (shift_amt + 2) / 2 + 1  (approximately)
        # recovery = 32 - shift_amt
        
        # Simplified approach: use shift_amt to compute parameters
        iter_from_shift = ((shift_amt.bitcast(UInt(6)) + Bits(6)(3)) >> 1).bitcast(Bits(6))
        
        # Normalize divisor by shifting left
        divisor_shifted = Bits(35)(0)
        for s in range(32):
            is_shift = (shift_amt == Bits(6)(s))
            if s == 0:
                shifted_val = concat(Bits(3)(0), divisor)
            else:
                shifted_val = concat(Bits(3)(0), divisor[0:31-s], Bits(s)(0)) if s < 32 else Bits(35)(0)
            divisor_shifted = is_shift.select(shifted_val, divisor_shifted)
        
        # For dividend: alternate between padding with 0 and with dividend<<1
        # Based on whether shift_amt is even or odd
        shift_odd = shift_amt[0:0] == Bits(1)(1)
        dividend_padded = shift_odd.select(
            concat(Bits(5)(0), dividend, Bits(1)(0)),
            concat(Bits(6)(0), dividend)
        )
        
        # Apply the low-bit cases
        divisor_star = d_low.select(divisor_shifted, divisor_star)
        dividend_star = d_low.select(dividend_padded, dividend_star)
        iterations = d_low.select(iter_from_shift[0:4], iterations)
        recovery = d_low.select((Bits(6)(32).bitcast(UInt(6)) - shift_amt.bitcast(UInt(6))).bitcast(Bits(6)), recovery)
        
        return (divisor_star, dividend_star, iterations, recovery)

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
        with Condition(self.state[0] == self.DIV_PRE):
            # Perform pre-processing: normalize divisor and dividend
            divisor_star, dividend_star, iters, recov = self.pre_process(
                self.divisor_r[0], self.dividend_r[0]
            )
            
            # Store normalized divisor (36 bits with padding)
            # divisor_star is 35-bit, we need to extend to 36 bits and shift left by 1
            self.divisor_norm[0] = concat(divisor_star, Bits(1)(0))
            
            # Initialize partial remainder from dividend_star
            # dividend_star is 38 bits, we take the lower 36 bits
            self.w_reg[0] = dividend_star[0:35]
            
            # Store iteration count and recovery shift
            self.iterations[0] = iters
            self.recovery[0] = recov
            self.div_cnt[0] = iters
            
            # Initialize Q/QM for on-the-fly conversion
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0)
            
            # Initialize quotient register for compatibility
            self.quotient[0] = Bits(32)(0)
            self.remainder[0] = Bits(34)(0)

            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING

            debug_log("SRT4Divider: Preprocessing complete, iterations={}", iters)

        # State: DIV_WORKING - Iterative SRT-4 division
        # Uses QDS table lookup and on-the-fly quotient conversion
        with Condition(self.state[0] == self.DIV_WORKING):
            # Check if this is the last iteration
            is_last_iter = (self.div_cnt[0] == Bits(5)(1))
            
            # Get QDS table inputs
            # dividend_index: 7-bit signed from w_reg[35:29] (top 7 bits)
            # Note: In Verilog, it's w_reg[DW+3:DW-3] where DW=32, so bits [35:29]
            dividend_index = self.w_reg[0][29:35]  # 7 bits
            
            # divisor_index: 4-bit from normalized divisor bits [32:29]
            # In Verilog: divisor_reg[DW:DW-3] where DW=32, so bits [32:29]
            divisor_index = self.divisor_norm[0][29:32]  # 4 bits
            
            # Look up quotient digit magnitude from QDS table
            q_table = self.qds_table(dividend_index, divisor_index)
            
            # q_in encoding: {sign_bit, q_table}
            # sign_bit is dividend_index[6] (MSB of 7-bit signed value)
            sign_bit = dividend_index[6:6]
            q_in = concat(sign_bit, q_table)
            
            # Compute divisor multiples (36-bit arithmetic)
            divisor_real = self.divisor_norm[0]
            divisor_2_real = concat(self.divisor_norm[0][0:34], Bits(1)(0))  # divisor << 1
            divisor_neg = (~self.divisor_norm[0] + Bits(36)(1)).bitcast(Bits(36))  # -divisor
            divisor_2_neg = (~divisor_2_real + Bits(36)(1)).bitcast(Bits(36))  # -2*divisor
            
            # Compute w_next_temp based on q_in
            # q_in = 001 (+1): w_next_temp = w_reg - divisor
            # q_in = 010 (+2): w_next_temp = w_reg - 2*divisor
            # q_in = 101 (-1): w_next_temp = w_reg + divisor
            # q_in = 110 (-2): w_next_temp = w_reg + 2*divisor
            # q_in = x00 (0):  w_next_temp = w_reg
            
            is_q_pos1 = (q_in == Bits(3)(0b001))
            is_q_pos2 = (q_in == Bits(3)(0b010))
            is_q_neg1 = (q_in == Bits(3)(0b101))
            is_q_neg2 = (q_in == Bits(3)(0b110))
            is_q_0 = (q_table == Bits(2)(0b00))
            
            w_reg_val = self.w_reg[0]
            
            # Compute w_next_temp for each case
            w_q_pos1 = (w_reg_val.bitcast(UInt(36)) + divisor_neg.bitcast(UInt(36))).bitcast(Bits(36))
            w_q_pos2 = (w_reg_val.bitcast(UInt(36)) + divisor_2_neg.bitcast(UInt(36))).bitcast(Bits(36))
            w_q_neg1 = (w_reg_val.bitcast(UInt(36)) + divisor_real.bitcast(UInt(36))).bitcast(Bits(36))
            w_q_neg2 = (w_reg_val.bitcast(UInt(36)) + divisor_2_real.bitcast(UInt(36))).bitcast(Bits(36))
            
            w_next_temp = is_q_pos1.select(
                w_q_pos1,
                is_q_pos2.select(
                    w_q_pos2,
                    is_q_neg1.select(
                        w_q_neg1,
                        is_q_neg2.select(
                            w_q_neg2,
                            w_reg_val  # q = 0
                        )
                    )
                )
            )
            
            # w_next = w_next_temp << 2 (for next iteration)
            w_next = concat(w_next_temp[0:33], Bits(2)(0))
            
            # On-the-fly conversion for Q and QM registers
            # Based on Verilog on_the_fly_conversion.v
            Q_cur = self.Q[0]
            QM_cur = self.QM[0]
            
            # q_in encodings:
            # 010 (+2): QM = Q<<2|01, Q = Q<<2|10
            # 001 (+1): QM = Q<<2|00, Q = Q<<2|01
            # x00 (0):  QM = QM<<2|11, Q = Q<<2|00
            # 101 (-1): QM = QM<<2|10, Q = QM<<2|11
            # 110 (-2): QM = QM<<2|01, Q = QM<<2|10
            
            Q_shifted = concat(Q_cur[0:29], Bits(2)(0))
            QM_shifted = concat(QM_cur[0:29], Bits(2)(0))
            
            new_QM = is_q_pos2.select(
                concat(Q_cur[0:29], Bits(2)(0b01)),    # q=+2
                is_q_pos1.select(
                    concat(Q_cur[0:29], Bits(2)(0b00)),    # q=+1
                    is_q_0.select(
                        concat(QM_cur[0:29], Bits(2)(0b11)),   # q=0
                        is_q_neg1.select(
                            concat(QM_cur[0:29], Bits(2)(0b10)),   # q=-1
                            concat(QM_cur[0:29], Bits(2)(0b01))    # q=-2
                        )
                    )
                )
            )
            
            new_Q = is_q_pos2.select(
                concat(Q_cur[0:29], Bits(2)(0b10)),    # q=+2
                is_q_pos1.select(
                    concat(Q_cur[0:29], Bits(2)(0b01)),    # q=+1
                    is_q_0.select(
                        concat(Q_cur[0:29], Bits(2)(0b00)),    # q=0
                        is_q_neg1.select(
                            concat(QM_cur[0:29], Bits(2)(0b11)),   # q=-1
                            concat(QM_cur[0:29], Bits(2)(0b10))    # q=-2
                        )
                    )
                )
            )
            
            # Update registers based on whether this is the last iteration
            with Condition(is_last_iter):
                # Last iteration: store w_next_temp (not shifted)
                self.w_reg[0] = w_next_temp
                self.state[0] = self.DIV_END
                debug_log("SRT4Divider: Last iteration complete")
            
            with Condition(~is_last_iter):
                # Not last: store w_next (shifted) for next iteration
                self.w_reg[0] = w_next
            
            # Always update Q, QM, and counter
            self.Q[0] = new_Q
            self.QM[0] = new_QM
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))

        # State: DIV_END - Post-processing for SRT-4
        with Condition(self.state[0] == self.DIV_END):
            # SRT-4 post-processing based on Verilog reference:
            # 1. If final w_reg is negative, fix quotient and remainder
            # 2. Recover remainder by shifting based on recovery value
            # 3. Apply sign correction for signed division
            
            # Check if w_reg is negative (sign bit set)
            w_reg_negative = self.w_reg[0][35:35] == Bits(1)(1)
            
            # Get normalized divisor for correction
            divisor_real = self.divisor_norm[0]
            
            # Fix quotient and remainder if w_reg is negative
            # q_out_fix = w_reg_negative ? Q - 1 : Q
            # w_reg_fix = w_reg_negative ? w_reg + divisor : w_reg
            q_out_raw = self.Q[0]
            q_out_fix = w_reg_negative.select(
                (q_out_raw.bitcast(UInt(32)) - Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32)),
                q_out_raw
            )
            
            w_reg_fix = w_reg_negative.select(
                (self.w_reg[0].bitcast(UInt(36)) + divisor_real.bitcast(UInt(36))).bitcast(Bits(36)),
                self.w_reg[0]
            )
            
            # Recover remainder by shifting right based on recovery value
            # In Verilog: reminder_temp = w_reg_fix << recovery_reg; reminder = reminder_temp[DW+32:DW+1]
            # For 32-bit result, we shift w_reg_fix and extract the high bits
            # Since w_reg_fix is 36 bits and result is 32 bits, we need proper extraction
            
            # Simplified recovery: just take the relevant bits of w_reg_fix
            # The recovery shift compensates for the normalization
            recovery_val = self.recovery[0]
            
            # For remainder recovery, shift w_reg_fix right by (33 - recovery_val)
            # This aligns the remainder to the correct position
            # In the Verilog, it does: (w_reg_fix << recovery) >> 33
            # We'll compute the 32-bit remainder directly
            
            # w_reg_fix is in 36-bit format with extra precision
            # The actual remainder value is in the upper portion
            # Based on Verilog: reminder = (w_reg_fix << recovery_reg) >> 33
            
            # For simplicity, we compute remainder as w_reg_fix shifted appropriately
            # The shift amount depends on recovery value
            rem_raw = Bits(32)(0)
            for r in range(33):
                is_this_recovery = (recovery_val == Bits(6)(r))
                # Shift w_reg_fix left by r, then take bits [35:4] as remainder candidate
                if r == 0:
                    shifted = w_reg_fix
                else:
                    # Left shift by r bits
                    shifted = concat(w_reg_fix[0:35-r], Bits(r)(0)) if r < 36 else Bits(36)(0)
                # Take the high 32 bits after shifting
                rem_candidate = shifted[4:35]  # bits [35:4] gives us 32 bits
                rem_raw = is_this_recovery.select(rem_candidate, rem_raw)
            
            debug_log("SRT4Divider: DIV_END - Q=0x{:x}, w_reg=0x{:x}", 
                self.Q[0], self.w_reg[0][0:31])
            debug_log("SRT4Divider: q_out_fix=0x{:x}, rem_raw=0x{:x}", q_out_fix, rem_raw)

            # Store results for compatibility
            self.quotient[0] = q_out_fix
            self.remainder[0] = concat(Bits(2)(0), rem_raw)

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
                    (~q_out_fix + Bits(32)(1)).bitcast(Bits(32)),
                    q_out_fix
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~rem_raw + Bits(32)(1)).bitcast(Bits(32)),
                    rem_raw
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
