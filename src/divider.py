"""
SRT-4 Divider for RV32IM Division Instructions

This module implements a true SRT-4 (Sweeney-Robertson-Tocher) division algorithm
based on the Verilog reference implementation in srt4/ directory.

Architecture Overview:
=====================

The SRT-4 divider uses:
1. Divisor normalization - shift divisor to place MSB at bit 31
2. QDS (Quotient Digit Selection) table lookup - based on partial remainder
3. Redundant quotient digit set {-2, -1, 0, +1, +2}
4. On-the-fly conversion using Q/QM registers

Key SRT-4 Features:
- No need to compute 3×d (hardware advantage over Radix-4)
- Variable iteration count based on divisor normalization
- Signed partial remainder handling

QDS Table (from radix4_table.v):
- Input: 7-bit signed dividend_index (w_reg[35:29])
- Input: 4-bit divisor_index (divisor[32:29], always 1xxx after normalization)
- Output: 2-bit magnitude (00=0, 01=1, 10=2)
- Sign determined by dividend_index[6]

On-the-fly Conversion (from on_the_fly_conversion.v):
- q=+2 (010): Q=Q<<2|10, QM=Q<<2|01
- q=+1 (001): Q=Q<<2|01, QM=Q<<2|00
- q=0  (x00): Q=Q<<2|00, QM=QM<<2|11
- q=-1 (101): Q=QM<<2|11, QM=QM<<2|10
- q=-2 (110): Q=QM<<2|10, QM=QM<<2|01

Timing:
- 1 cycle: Preprocessing (DIV_PRE) - normalize divisor, compute iterations
- 1-17 cycles: Iterative calculation (DIV_WORKING) - 2 bits per cycle
- 1 cycle: Post-processing (DIV_END) - remainder correction, sign fixup
- Total: ~18 cycles for normal division

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class SRT4Divider:
    """
    True SRT-4 division implementation based on Verilog reference in srt4/.

    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (normalize divisor, compute iterations)
    - 1-17 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (remainder correction, sign fixup)

    Key SRT-4 features:
    - Redundant quotient digit set {-2, -1, 0, +1, +2}
    - QDS table lookup based on partial remainder and normalized divisor
    - On-the-fly quotient conversion using Q/QM registers
    - No 3×divisor computation needed (hardware advantage)

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
        
        # SRT-4 specific registers (from Verilog reference)
        self.w_reg = RegArray(Bits(36), 1, initializer=[0])      # Partial remainder (36 bits)
        self.divisor_reg = RegArray(Bits(36), 1, initializer=[0])  # Normalized divisor (36 bits)
        self.iterations_reg = RegArray(Bits(5), 1, initializer=[0])  # Iteration count
        self.recovery_reg = RegArray(Bits(6), 1, initializer=[0])  # Recovery shift amount

        # On-the-fly conversion registers
        self.Q = RegArray(Bits(32), 1, initializer=[0])
        self.QM = RegArray(Bits(32), 1, initializer=[0])

        # Sign tracking for final correction
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])  # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])  # Sign flag for result
        
        # Compatibility registers for tests
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])  # Normalization shift amount
        self.shift_rem = RegArray(Bits(36), 1, initializer=[0])  # Shifted remainder
        self.quotient = RegArray(Bits(32), 1, initializer=[0])  # For legacy access
        self.remainder = RegArray(Bits(34), 1, initializer=[0])  # For legacy access

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

    def quotient_select(self, w_high):
        """Compatibility placeholder for quotient selection"""
        return Bits(3)(0)
    
    def qds_table(self, dividend_index, divisor_index):
        """
        QDS (Quotient Digit Selection) table lookup.
        Based on radix4_table.v from Verilog reference.
        
        Args:
            dividend_index: 7-bit signed value from w_reg[35:29]
            divisor_index: 4-bit value from divisor_reg[32:29] (always 1xxx after normalization)
            
        Returns:
            (q_sign, q_magnitude) where:
            - q_sign: 1 if negative, 0 if positive/zero
            - q_magnitude: 2-bit value (00=0, 01=1, 10=2)
        """
        # Get sign of dividend_index (bit 6)
        div_idx_sign = dividend_index[6:6]
        
        # For signed comparison, convert to Python-style comparisons using explicit bounds
        # dividend_index is 7-bit two's complement: range -64 to +63
        
        # Check divisor_index patterns (always 1xxx after normalization, so 8-15)
        d_1000 = (divisor_index == Bits(4)(0b1000))
        d_1001 = (divisor_index == Bits(4)(0b1001))
        d_1010 = (divisor_index == Bits(4)(0b1010))
        d_1011 = (divisor_index == Bits(4)(0b1011))
        d_1100 = (divisor_index == Bits(4)(0b1100))
        d_1101 = (divisor_index == Bits(4)(0b1101))
        d_1110 = (divisor_index == Bits(4)(0b1110))
        d_1111 = (divisor_index == Bits(4)(0b1111))
        
        # Comparison thresholds (7-bit signed)
        # For positive values, use unsigned comparison
        # For negative values, check sign bit and magnitude
        
        # Positive thresholds
        x_ge_4 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(4))
        x_ge_6 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(6))
        x_ge_8 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(8))
        x_ge_12 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(12))
        x_ge_14 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(14))
        x_ge_15 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(15))
        x_ge_16 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(16))
        x_ge_18 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(18))
        x_ge_20 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(20))
        x_ge_24 = (div_idx_sign == Bits(1)(0)) & (dividend_index[0:5] >= Bits(6)(24))
        
        # For negative thresholds (x >= -N), need to check:
        # If x is positive: always true
        # If x is negative: magnitude <= N (in two's complement)
        # Note: -4 in 7-bit is 0b1111100 (124 unsigned), -13 is 0b1110011 (115)
        
        # x >= -4 means: positive OR (negative AND magnitude <= 4)
        # In two's complement, -4 = 0b1111100, so check if value >= 0b1111100 (as unsigned)
        x_ge_neg4 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1111100))
        x_ge_neg6 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1111010))
        x_ge_neg8 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1111000))
        x_ge_neg13 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1110011))
        x_ge_neg15 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1110001))
        x_ge_neg16 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1110000))
        x_ge_neg18 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1101110))
        x_ge_neg20 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1101100))
        x_ge_neg22 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1101010))
        x_ge_neg24 = (div_idx_sign == Bits(1)(0)) | (dividend_index >= Bits(7)(0b1101000))
        
        # QDS table logic for each divisor value
        # d=1000 (8): q=2 if x>=12, q=1 if 4<=x<12, q=0 if -4<x<4, q=-1 if -13<=x<-4, q=-2 if x<-13
        d_1000_q_2 = d_1000 & x_ge_12
        d_1000_q_1 = d_1000 & x_ge_4 & ~x_ge_12
        d_1000_q_0 = d_1000 & x_ge_neg4 & ~x_ge_4
        d_1000_q_neg1 = d_1000 & x_ge_neg13 & ~x_ge_neg4
        d_1000_q_neg2 = d_1000 & ~x_ge_neg13
        
        # d=1001 (9): q=2 if x>=14, q=1 if 4<=x<14, q=0 if -6<x<4, q=-1 if -15<=x<-6, q=-2 if x<-15
        d_1001_q_2 = d_1001 & x_ge_14
        d_1001_q_1 = d_1001 & x_ge_4 & ~x_ge_14
        d_1001_q_0 = d_1001 & x_ge_neg6 & ~x_ge_4
        d_1001_q_neg1 = d_1001 & x_ge_neg15 & ~x_ge_neg6
        d_1001_q_neg2 = d_1001 & ~x_ge_neg15
        
        # d=1010 (10): q=2 if x>=15, q=1 if 4<=x<15, q=0 if -6<x<4, q=-1 if -16<=x<-6, q=-2 if x<-16
        d_1010_q_2 = d_1010 & x_ge_15
        d_1010_q_1 = d_1010 & x_ge_4 & ~x_ge_15
        d_1010_q_0 = d_1010 & x_ge_neg6 & ~x_ge_4
        d_1010_q_neg1 = d_1010 & x_ge_neg16 & ~x_ge_neg6
        d_1010_q_neg2 = d_1010 & ~x_ge_neg16
        
        # d=1011 (11): q=2 if x>=16, q=1 if 4<=x<16, q=0 if -6<x<4, q=-1 if -18<=x<-6, q=-2 if x<-18
        d_1011_q_2 = d_1011 & x_ge_16
        d_1011_q_1 = d_1011 & x_ge_4 & ~x_ge_16
        d_1011_q_0 = d_1011 & x_ge_neg6 & ~x_ge_4
        d_1011_q_neg1 = d_1011 & x_ge_neg18 & ~x_ge_neg6
        d_1011_q_neg2 = d_1011 & ~x_ge_neg18
        
        # d=1100 (12): q=2 if x>=18, q=1 if 6<=x<18, q=0 if -8<x<6, q=-1 if -20<=x<-8, q=-2 if x<-20
        d_1100_q_2 = d_1100 & x_ge_18
        d_1100_q_1 = d_1100 & x_ge_6 & ~x_ge_18
        d_1100_q_0 = d_1100 & x_ge_neg8 & ~x_ge_6
        d_1100_q_neg1 = d_1100 & x_ge_neg20 & ~x_ge_neg8
        d_1100_q_neg2 = d_1100 & ~x_ge_neg20
        
        # d=1101 (13): q=2 if x>=20, q=1 if 6<=x<20, q=0 if -8<x<6, q=-1 if -20<=x<-8, q=-2 if x<-20
        d_1101_q_2 = d_1101 & x_ge_20
        d_1101_q_1 = d_1101 & x_ge_6 & ~x_ge_20
        d_1101_q_0 = d_1101 & x_ge_neg8 & ~x_ge_6
        d_1101_q_neg1 = d_1101 & x_ge_neg20 & ~x_ge_neg8
        d_1101_q_neg2 = d_1101 & ~x_ge_neg20
        
        # d=1110 (14): q=2 if x>=20, q=1 if 8<=x<20, q=0 if -8<x<8, q=-1 if -22<=x<-8, q=-2 if x<-22
        d_1110_q_2 = d_1110 & x_ge_20
        d_1110_q_1 = d_1110 & x_ge_8 & ~x_ge_20
        d_1110_q_0 = d_1110 & x_ge_neg8 & ~x_ge_8
        d_1110_q_neg1 = d_1110 & x_ge_neg22 & ~x_ge_neg8
        d_1110_q_neg2 = d_1110 & ~x_ge_neg22
        
        # d=1111 (15): q=2 if x>=24, q=1 if 8<=x<20, q=0 if -8<x<8, q=-1 if -24<=x<-8, q=-2 if x<-24
        d_1111_q_2 = d_1111 & x_ge_24
        d_1111_q_1 = d_1111 & x_ge_8 & ~x_ge_20  # Note: same as d_1110 upper bound
        d_1111_q_0 = d_1111 & x_ge_neg8 & ~x_ge_8
        d_1111_q_neg1 = d_1111 & x_ge_neg24 & ~x_ge_neg8
        d_1111_q_neg2 = d_1111 & ~x_ge_neg24
        
        # Combine all conditions
        q_2 = d_1000_q_2 | d_1001_q_2 | d_1010_q_2 | d_1011_q_2 | d_1100_q_2 | d_1101_q_2 | d_1110_q_2 | d_1111_q_2
        q_1 = d_1000_q_1 | d_1001_q_1 | d_1010_q_1 | d_1011_q_1 | d_1100_q_1 | d_1101_q_1 | d_1110_q_1 | d_1111_q_1
        q_0 = d_1000_q_0 | d_1001_q_0 | d_1010_q_0 | d_1011_q_0 | d_1100_q_0 | d_1101_q_0 | d_1110_q_0 | d_1111_q_0
        q_neg1 = d_1000_q_neg1 | d_1001_q_neg1 | d_1010_q_neg1 | d_1011_q_neg1 | d_1100_q_neg1 | d_1101_q_neg1 | d_1110_q_neg1 | d_1111_q_neg1
        q_neg2 = d_1000_q_neg2 | d_1001_q_neg2 | d_1010_q_neg2 | d_1011_q_neg2 | d_1100_q_neg2 | d_1101_q_neg2 | d_1110_q_neg2 | d_1111_q_neg2
        
        # Output magnitude (2 bits): 10=2, 01=1, 00=0
        q_magnitude = (q_2 | q_neg2).select(
            Bits(2)(0b10),
            (q_1 | q_neg1).select(
                Bits(2)(0b01),
                Bits(2)(0b00)
            )
        )
        
        return (div_idx_sign, q_magnitude)

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
            # SRT-4 preprocessing: normalize divisor so MSB is at bit 31
            # This ensures divisor_index (bits [32:29]) is always 1xxx (8-15)
            
            divisor = self.divisor_r[0]
            dividend = self.dividend_r[0]
            
            # Find leading 1 position to determine shift amount
            # Based on pre_processing.v case statement
            leading_one = self.find_leading_one(divisor)
            
            # Calculate shift amount to normalize (31 - leading_one_position)
            # After normalization, divisor will have MSB at bit 31
            
            # Normalize divisor and dividend based on leading 1 position
            # From pre_processing.v: divisor is left-shifted to place MSB at bit 31
            # dividend_star has specific formatting based on leading 1 position
            
            # Generate shift amount and iterations for each case
            # We'll use a simplified approach: compute based on leading 1 position
            
            # Iteration count formula from pre_processing.v:
            # - If leading 1 at bit 31: 1 iteration
            # - If leading 1 at bit 30: 2 iterations  
            # - Generally: ceil((32 - leading_one_pos) / 2) iterations
            
            # Recovery is the bit position + 1 (used for remainder de-normalization)
            
            # For simplicity, use a single computation path based on shift amount
            shift_amt = Bits(6)(31).bitcast(UInt(6)) - leading_one.bitcast(UInt(6))
            shift_amt_bits = shift_amt.bitcast(Bits(6))
            
            # Store shift amount for compatibility
            self.div_shift[0] = shift_amt_bits
            
            # Normalize divisor (shift left so MSB is at bit 31)
            # We need to build the shifted divisor for each possible shift amount
            divisor_shifted = divisor
            for s in range(32):
                with Condition(shift_amt_bits == Bits(6)(s)):
                    if s < 31:
                        divisor_shifted = concat(divisor[0:30-s], Bits(s+1)(0))
                    else:
                        divisor_shifted = concat(Bits(1)(0), Bits(31)(0))
            
            # Extend to 36 bits with extra bit for sign
            divisor_36 = concat(Bits(4)(0), divisor_shifted)
            
            # Initialize w_reg with dividend (extended to 36 bits)
            # From pre_processing.v: dividend_star format depends on shift parity
            # For even shift: dividend_star = {2'b0, dividend, 1'b0}
            # For odd shift:  dividend_star = {3'b0, dividend}
            shift_is_odd = shift_amt_bits[0:0]
            w_init = shift_is_odd.select(
                concat(Bits(4)(0), dividend),  # Odd: {4'b0, dividend} -> 36 bits
                concat(Bits(3)(0), dividend, Bits(1)(0))  # Even: {3'b0, dividend, 1'b0} -> 36 bits
            )
            
            # Compute iterations: ceil((shift_amt + 1) / 2) + 1
            # Based on pre_processing.v case statements
            iterations = ((shift_amt_bits.bitcast(UInt(6)) + UInt(6)(1)) >> UInt(6)(1)).bitcast(Bits(5)) + Bits(5)(1)
            
            # Recovery value (for de-normalizing remainder at the end)
            recovery = Bits(6)(32).bitcast(UInt(6)) - shift_amt.bitcast(UInt(6))
            
            # Store normalized values
            self.w_reg[0] = w_init
            self.divisor_reg[0] = divisor_36
            self.iterations_reg[0] = iterations
            self.recovery_reg[0] = recovery.bitcast(Bits(6))
            self.div_cnt[0] = iterations
            
            # Initialize Q/QM for on-the-fly conversion
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0)
            
            # Initialize legacy registers
            self.quotient[0] = Bits(32)(0)
            self.remainder[0] = Bits(34)(0)
            
            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING
            
            debug_log("SRT4Divider: Preprocessing complete, shift={}, iterations={}",
                shift_amt_bits, iterations)

        # State: DIV_WORKING - SRT-4 iteration with QDS table and on-the-fly conversion
        # Based on srt_4_div.v main iteration loop
        with Condition(self.state[0] == self.DIV_WORKING):
            # Get current values
            w_cur = self.w_reg[0]  # 36-bit partial remainder
            divisor_cur = self.divisor_reg[0]  # 36-bit normalized divisor
            
            # Compute divisor multiples (36-bit signed)
            # divisor_real = divisor_cur (positive)
            # divisor_2_real = divisor_cur << 1
            # divisor_neg = -divisor_cur (two's complement)
            # divisor_2_neg = -divisor_2_real
            
            divisor_2 = concat(divisor_cur[0:34], Bits(1)(0))  # divisor * 2 (36 bits)
            
            # Two's complement negation for 36-bit values
            divisor_neg = (~divisor_cur + Bits(36)(1)).bitcast(Bits(36))
            divisor_2_neg = (~divisor_2 + Bits(36)(1)).bitcast(Bits(36))
            
            # Get dividend_index (7 bits from w_reg[35:29]) - this is signed
            dividend_index = w_cur[29:35]  # 7 bits
            
            # Get divisor_index (4 bits from divisor_reg[32:29])
            # After normalization, this should be 1xxx (8-15)
            divisor_index = divisor_cur[29:32]  # 4 bits
            
            # QDS table lookup
            q_sign, q_magnitude = self.qds_table(dividend_index, divisor_index)
            
            # Compute q_in (3-bit encoding): {sign, magnitude}
            # 010 = +2, 001 = +1, 000 = 0, 101 = -1, 110 = -2
            q_in = concat(q_sign, q_magnitude)
            
            # Compute w_next_temp based on q_in (before shifting)
            # From srt_4_div.v:
            # q=+1 (001): w_next_temp = divisor_neg + w_cur
            # q=+2 (010): w_next_temp = divisor_2_neg + w_cur
            # q=-1 (101): w_next_temp = divisor_real + w_cur
            # q=-2 (110): w_next_temp = divisor_2_real + w_cur
            # q=0  (x00): w_next_temp = w_cur
            
            is_q_pos_1 = (q_in == Bits(3)(0b001))
            is_q_pos_2 = (q_in == Bits(3)(0b010))
            is_q_neg_1 = (q_in == Bits(3)(0b101))
            is_q_neg_2 = (q_in == Bits(3)(0b110))
            is_q_zero = (q_magnitude == Bits(2)(0b00))
            
            w_next_temp = is_q_pos_1.select(
                (w_cur.bitcast(UInt(36)) + divisor_neg.bitcast(UInt(36))).bitcast(Bits(36)),
                is_q_pos_2.select(
                    (w_cur.bitcast(UInt(36)) + divisor_2_neg.bitcast(UInt(36))).bitcast(Bits(36)),
                    is_q_neg_1.select(
                        (w_cur.bitcast(UInt(36)) + divisor_cur.bitcast(UInt(36))).bitcast(Bits(36)),
                        is_q_neg_2.select(
                            (w_cur.bitcast(UInt(36)) + divisor_2.bitcast(UInt(36))).bitcast(Bits(36)),
                            w_cur  # q=0
                        )
                    )
                )
            )
            
            # w_next = w_next_temp << 2 (for non-final iterations)
            w_next = concat(w_next_temp[0:33], Bits(2)(0))
            
            # On-the-fly conversion (from on_the_fly_conversion.v)
            # q_in_010 (+2): Q=Q<<2|10, QM=Q<<2|01
            # q_in_001 (+1): Q=Q<<2|01, QM=Q<<2|00
            # q_in_x00 (0):  Q=Q<<2|00, QM=QM<<2|11
            # q_in_101 (-1): Q=QM<<2|11, QM=QM<<2|10
            # q_in_110 (-2): Q=QM<<2|10, QM=QM<<2|01
            
            Q_cur = self.Q[0]
            QM_cur = self.QM[0]
            
            new_Q = is_q_pos_2.select(
                concat(Q_cur[0:29], Bits(2)(0b10)),
                is_q_pos_1.select(
                    concat(Q_cur[0:29], Bits(2)(0b01)),
                    is_q_zero.select(
                        concat(Q_cur[0:29], Bits(2)(0b00)),
                        is_q_neg_1.select(
                            concat(QM_cur[0:29], Bits(2)(0b11)),
                            concat(QM_cur[0:29], Bits(2)(0b10))  # q=-2
                        )
                    )
                )
            )
            
            new_QM = is_q_pos_2.select(
                concat(Q_cur[0:29], Bits(2)(0b01)),
                is_q_pos_1.select(
                    concat(Q_cur[0:29], Bits(2)(0b00)),
                    is_q_zero.select(
                        concat(QM_cur[0:29], Bits(2)(0b11)),
                        is_q_neg_1.select(
                            concat(QM_cur[0:29], Bits(2)(0b10)),
                            concat(QM_cur[0:29], Bits(2)(0b01))  # q=-2
                        )
                    )
                )
            )
            
            # Check if this is the last iteration
            is_last = (self.div_cnt[0] == Bits(5)(1))
            
            # Update w_reg: use w_next_temp (not shifted) for final iteration
            self.w_reg[0] = is_last.select(w_next_temp, w_next)
            
            # Update Q/QM registers
            self.Q[0] = new_Q
            self.QM[0] = new_QM
            
            # Update shift_rem for compatibility
            self.shift_rem[0] = w_next_temp
            
            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))
            
            # Check if done
            with Condition(is_last):
                self.state[0] = self.DIV_END
                debug_log("SRT4Divider: Last iteration complete")

        # State: DIV_END - Post-processing for SRT-4
        # Based on srt_4_div.v post-processing
        with Condition(self.state[0] == self.DIV_END):
            # SRT-4 post-processing:
            # 1. Fix negative remainder (if w_reg[35] is 1)
            # 2. De-normalize remainder using recovery shift
            # 3. Apply sign correction for signed division
            
            w_final = self.w_reg[0]  # 36-bit final partial remainder
            divisor_cur = self.divisor_reg[0]  # 36-bit normalized divisor
            
            # Check if remainder is negative (sign bit set)
            w_is_negative = (w_final[35:35] == Bits(1)(1))
            
            # Fix negative remainder: if negative, Q = Q - 1, w = w + d
            q_raw = self.Q[0]
            q_fixed = w_is_negative.select(
                (q_raw.bitcast(UInt(32)) - UInt(32)(1)).bitcast(Bits(32)),
                q_raw
            )
            
            w_fixed = w_is_negative.select(
                (w_final.bitcast(UInt(36)) + divisor_cur.bitcast(UInt(36))).bitcast(Bits(36)),
                w_final
            )
            
            # De-normalize remainder: shift right by (32 - recovery) and take upper bits
            # From srt_4_div.v: reminder_temp = ({28'b0, w_reg_fix} << recovery_reg)
            # reminder = reminder_temp[DW+32:DW+1] (for DW=32, this is bits [64:33])
            #
            # Simplified: remainder = w_fixed >> (36 - recovery) shifted to get actual value
            # The remainder is in w_fixed, we need to extract the correct bits
            
            recovery = self.recovery_reg[0]
            
            # For remainder recovery, we need to shift the remainder based on recovery
            # The upper bits of w_fixed contain the remainder, scaled by the normalization
            # remainder = w_fixed[35:4] >> (32 - recovery)  
            #
            # Simpler approach: just use the upper 32 bits, shifted appropriately
            # remainder_raw = w_fixed[35:4] (32 bits from upper part)
            
            # Since we normalized divisor, the remainder is also scaled
            # To de-normalize: right shift by the same amount we left-shifted divisor
            # shift_amt = 31 - leading_one_position = recovery - 1 (approximately)
            
            # From the Verilog: remainder is extracted as upper bits after proper shift
            # For simplicity, we extract remainder from w_fixed upper bits
            rem_raw_36 = w_fixed
            
            # Generate de-normalized remainder for each recovery value
            rem_out = Bits(32)(0)
            for r in range(1, 34):
                with Condition(recovery == Bits(6)(r)):
                    # Shift and mask to get correct remainder
                    # recovery = 32 means no shift needed (divisor was already normalized)
                    # recovery = 1 means shift left by 31 to denormalize (divisor had MSB at bit 0)
                    if r <= 32:
                        # Extract upper bits and shift  
                        # remainder = w_fixed >> (36 - r - 4) truncated to 32 bits
                        shift_right = 36 - r - 4
                        if shift_right >= 0 and shift_right < 36:
                            rem_out = rem_raw_36[shift_right:shift_right + 31]
            
            # Use Q register for quotient output
            q_out = q_fixed
            
            debug_log("SRT4Divider: DIV_END - quotient=0x{:x}, remainder=0x{:x}, w_neg={}",
                q_out, rem_out, w_is_negative)

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
            
            # Update legacy registers for compatibility
            self.quotient[0] = q_fixed
            self.remainder[0] = concat(Bits(2)(0), rem_out)

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