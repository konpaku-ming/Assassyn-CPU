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
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])   # Unsigned divisor
        self.div_shift = RegArray(Bits(5), 1, initializer=[0])    # Alignment shift amount
        self.shift_rem = RegArray(Bits(65), 1, initializer=[0])   # Partial remainder (2*WID+1 = 65 bits)
        self.Q = RegArray(Bits(33), 1, initializer=[0])           # Quotient accumulator (WID+1 = 33 bits)
        self.QM = RegArray(Bits(33), 1, initializer=[0])          # Quotient-1 accumulator
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])     # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])       # Sign flag for result
        
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
        
        log("Divider: Start {} division, dividend=0x{:x}, divisor=0x{:x}",
            is_signed.select("signed", "unsigned"),
            dividend,
            divisor)
    
    def find_leading_one(self, d):
        """
        Find position of leading 1 in divisor (implements find_1.v logic).
        Returns the bit position for normalization.
        
        This implements the same logic as find_1.v module:
        - Finds the position of the most significant 1 bit
        - Used for divisor alignment to minimize iterations
        
        Args:
            d: 32-bit divisor
            
        Returns:
            Position of leading 1 (0-31), or 0 if all zeros
        """
        # Implementation using priority encoder logic with select chain
        # Start from position 0 and update if we find a 1 at higher position
        pos = Bits(5)(0)
        
        # Check each bit from LSB to MSB, updating pos when we find a 1
        # This creates a priority encoder where higher bits take precedence
        for i in range(0, 32):
            bit_set = (d[i:i] == Bits(1)(1))
            pos = bit_set.select(Bits(5)(i), pos)
        
        return pos
    
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
        table_8  = (d_high == Bits(4)(0b1000))
        table_9  = (d_high == Bits(4)(0b1001))
        table_10 = (d_high == Bits(4)(0b1010))
        table_11 = (d_high == Bits(4)(0b1011))
        table_12 = (d_high == Bits(4)(0b1100))
        table_13 = (d_high == Bits(4)(0b1101))
        table_14 = (d_high == Bits(4)(0b1110))
        table_15 = (d_high == Bits(4)(0b1111))
        
        # Determine if quotient should be negative
        # Based on rem_high ranges for each table
        neg = (table_8  & ((rem_high >= Bits(6)(0b110100)) & (rem_high < Bits(6)(0b111110)))) | \
              (table_9  & ((rem_high >= Bits(6)(0b110010)) & (rem_high < Bits(6)(0b111101)))) | \
              (table_10 & ((rem_high >= Bits(6)(0b110001)) & (rem_high < Bits(6)(0b111101)))) | \
              (table_11 & ((rem_high >= Bits(6)(0b110000)) & (rem_high < Bits(6)(0b111101)))) | \
              (table_12 & ((rem_high >= Bits(6)(0b101110)) & (rem_high < Bits(6)(0b111100)))) | \
              (table_13 & ((rem_high >= Bits(6)(0b101101)) & (rem_high < Bits(6)(0b111100)))) | \
              (table_14 & ((rem_high >= Bits(6)(0b101100)) & (rem_high < Bits(6)(0b111100)))) | \
              (table_15 & ((rem_high >= Bits(6)(0b101010)) & (rem_high < Bits(6)(0b111100))))
        
        # Determine if quotient digit is 2
        q2 = (table_8  & (((rem_high >= Bits(6)(0b110100)) & (rem_high < Bits(6)(0b111010))) | \
                          ((rem_high >= Bits(6)(0b000110)) & (rem_high <= Bits(6)(0b001011))))) | \
             (table_9  & (((rem_high >= Bits(6)(0b110010)) & (rem_high < Bits(6)(0b111001))) | \
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
        q0 = (table_8  & (((rem_high >= Bits(6)(0b111110)) & (rem_high <= Bits(6)(0b111111))) | \
                          ((rem_high >= Bits(6)(0)) & (rem_high < Bits(6)(0b000010))))) | \
             (table_9  & (((rem_high >= Bits(6)(0b111101)) & (rem_high <= Bits(6)(0b111111))) | \
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
                
                with ElseCondition(div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    log("Divider: Fast path (divisor=1)")
                
                with ElseCondition():
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
                Bits(32)(0xFFFFFFFF)   # 2^32-1 for unsigned (same bit pattern)
            )
            self.result[0] = self.is_rem[0].select(
                self.dividend_in[0],   # Remainder = dividend
                quotient_on_div0       # Quotient = -1 or 2^32-1
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
                Bits(32)(0),           # Remainder = 0
                self.dividend_in[0]    # Quotient = dividend
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
            
            # Initialize Q and QM
            self.Q[0] = Bits(33)(0)
            self.QM[0] = Bits(33)(0)
            
            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING
            
            # Initialize shift_rem: {33'b0, dividend_r} << (pos_1 + 1)
            # This is a 65-bit value
            dividend_extended = concat(Bits(33)(0), self.dividend_r[0])
            # Shift left by div_shift amount
            # For hardware, this would be a barrel shifter
            # For simulation, we use a simple shift
            shift_amount = (pos_1 + Bits(5)(1)).bitcast(UInt(5))
            self.shift_rem[0] = (dividend_extended.bitcast(UInt(65)) << shift_amount).bitcast(Bits(65))
            
            log("Divider: Preprocessing complete, shift={}, starting iterations", pos_1 + Bits(5)(1))
        
        # State: DIV_WORKING - Iterative SRT-4 calculation
        with Condition(self.state[0] == self.DIV_WORKING):
            # Extract high bits for quotient selection
            rem_high = self.shift_rem[0][64:59]  # Top 6 bits
            
            # Get high 4 bits of shifted divisor
            # shift_divisor = divisor_r << div_shift
            shift_amount = self.div_shift[0].bitcast(UInt(5))
            shift_divisor = ((self.divisor_r[0].bitcast(UInt(33)) << shift_amount) | Bits(33)(0)).bitcast(Bits(33))
            d_high = shift_divisor[32:29]  # Top 4 bits (bits 32:29 of 33-bit value)
            
            # Select quotient digit
            (q, neg) = self.quotient_select(rem_high, d_high)
            
            # Compute multiples of shift_divisor
            shift_divisor_n = (~shift_divisor + Bits(33)(1)).bitcast(Bits(33))  # -divisor
            shift_divisor_X2 = (shift_divisor.bitcast(UInt(33)) << Bits(5)(1)).bitcast(Bits(33))  # 2*divisor
            shift_divisor_X2n = (~shift_divisor_X2 + Bits(33)(1)).bitcast(Bits(33))  # -2*divisor
            
            # Update partial remainder based on q and neg
            # new_rem = (old_rem << 2) - q * divisor
            # Following SRT4.v logic: {shift_rem[62:30] + value, shift_rem[29:0], 2'b0}
            # shift_rem is 65 bits: [64:0]
            # High part: [64:32] = 33 bits -> after operation, still 33 bits
            # Low part to shift: [61:0] = 62 bits -> becomes [63:2] after left shift by 2
            rem_high_part = self.shift_rem[0][64:32]  # 33 bits for operation
            rem_low_part = self.shift_rem[0][61:0]    # 62 bits to preserve (will be shifted left)
            
            # Initialize new_rem_high to avoid unassigned variable
            new_rem_high = rem_high_part
            
            # Select the value to subtract based on q and neg
            # neg=0: q=0,1,2 -> subtract 0, divisor, 2*divisor
            # neg=1: q=0,1,2 -> add 0, divisor, 2*divisor (subtract negative)
            with Condition(neg == Bits(1)(0)):
                # Positive quotient digit
                with Condition(q == Bits(2)(0b00)):
                    new_rem_high = rem_high_part
                with Condition(q == Bits(2)(0b01)):
                    new_rem_high = (rem_high_part.bitcast(UInt(33)) + shift_divisor_n.bitcast(UInt(33))).bitcast(Bits(33))
                with Condition(q == Bits(2)(0b10)):
                    new_rem_high = (rem_high_part.bitcast(UInt(33)) + shift_divisor_X2n.bitcast(UInt(33))).bitcast(Bits(33))
            with ElseCondition():
                # Negative quotient digit (add instead of subtract)
                with Condition(q == Bits(2)(0b00)):
                    new_rem_high = rem_high_part
                with Condition(q == Bits(2)(0b01)):
                    new_rem_high = (rem_high_part.bitcast(UInt(33)) + shift_divisor.bitcast(UInt(33))).bitcast(Bits(33))
                with Condition(q == Bits(2)(0b10)):
                    new_rem_high = (rem_high_part.bitcast(UInt(33)) + shift_divisor_X2.bitcast(UInt(33))).bitcast(Bits(33))
            
            # Shift left by 2 (radix-4): concatenate new_rem_high (33 bits) with rem_low_part (62 bits)
            # Total: 33 + 62 = 95 bits, then take low 65 bits [64:0]
            # This is equivalent to: new_shift_rem = {new_rem_high, rem_low_part[61:0]}
            # which is already 33+62=95 bits, take [64:0] = shift right by 30 or take directly
            # Actually, we want: {new_rem_high[32:0], rem_low_part[61:0]} = 95 bits
            # Then [64:0] gives us the low 65 bits
            new_shift_rem = concat(new_rem_high, rem_low_part)  # 33 + 62 = 95 bits
            self.shift_rem[0] = new_shift_rem[64:0]  # Take low 65 bits
            
            # Update Q and QM accumulators
            # Q accumulator update based on sign of quotient digit
            with Condition(neg == Bits(1)(0)):
                # Positive quotient: Q = (Q << 2) | q
                self.Q[0] = concat(self.Q[0][30:0], q)
            with ElseCondition():
                # Negative quotient: Q = (QM << 2) | (~q & 0b11) | 0b100
                # This is equivalent to (QM << 2) + (4 - q)
                self.Q[0] = concat(self.QM[0][30:0], Bits(1)(1), q[0:0])
            
            # QM accumulator: QM = Q - 1
            # When neg=0 and q!=0: QM = (Q << 2) | (q-1)
            # Otherwise: QM = (QM << 2) | (~q & 0b11)
            with Condition((neg == Bits(1)(0)) & (q != Bits(2)(0))):
                # Positive and non-zero: QM gets Q's shifted value with q-1
                q_minus_1 = (q.bitcast(UInt(2)) - Bits(2)(1)).bitcast(Bits(2))
                self.QM[0] = concat(self.Q[0][30:0], q_minus_1)
            with ElseCondition():
                # QM gets shifted with complement of q
                self.QM[0] = concat(self.QM[0][30:0], ~q)
            
            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))
            
            # Check if done (counter reaches 0)
            with Condition(self.div_cnt[0] == Bits(5)(0)):
                self.state[0] = self.DIV_END
                log("Divider: Iterations complete, entering post-processing")
        
        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            # Adjust remainder if negative
            rem_is_negative = self.shift_rem[0][64:64]  # MSB of remainder
            
            # Get shifted divisor for adjustment
            shift_amount = self.div_shift[0].bitcast(UInt(5))
            shift_divisor = ((self.divisor_r[0].bitcast(UInt(33)) << shift_amount) | Bits(33)(0)).bitcast(Bits(33))
            
            with Condition(rem_is_negative == Bits(1)(1)):
                # Remainder is negative, need to adjust
                adjusted_rem = (self.shift_rem[0][64:32].bitcast(UInt(33)) + shift_divisor.bitcast(UInt(33))).bitcast(Bits(33))
                self.fin_rem[0] = adjusted_rem
                self.fin_q[0] = (self.Q[0].bitcast(UInt(33)) - Bits(33)(1)).bitcast(Bits(33))
            with ElseCondition():
                self.fin_rem[0] = self.shift_rem[0][64:32]
                self.fin_q[0] = self.Q[0]
            
            # Right-shift remainder back
            fin_rem_shifted = (self.fin_rem[0].bitcast(UInt(33)) >> shift_amount).bitcast(Bits(33))
            
            # Apply sign correction
            # For quotient: if signs differ, negate
            # For remainder: same sign as dividend
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]  # Dividend sign
            
            # Check for signed overflow: (-2^31) / (-1)
            min_int = Bits(32)(0x80000000)
            neg_one = Bits(32)(0xFFFFFFFF)
            signed_overflow = (self.sign_r[0] == Bits(1)(1)) & \
                             (self.dividend_in[0] == min_int) & \
                             (self.divisor_in[0] == neg_one)
            
            with Condition(signed_overflow):
                # Handle signed overflow per RISC-V spec
                self.result[0] = self.is_rem[0].select(
                    Bits(32)(0),           # Remainder = 0
                    Bits(32)(0x80000000)   # Quotient = -2^31 (no change)
                )
                log("Divider: Signed overflow detected (-2^31 / -1)")
            with ElseCondition():
                # Normal result with sign correction
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~self.fin_q[0][31:0] + Bits(32)(1)).bitcast(Bits(32)),
                    self.fin_q[0][31:0]
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~fin_rem_shifted[31:0] + Bits(32)(1)).bitcast(Bits(32)),
                    fin_rem_shifted[31:0]
                )
                
                # Select quotient or remainder
                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)
            
            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("Divider: Completed, result=0x{:x}", self.result[0])
    
    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, error)
        """
        return (self.ready[0], self.result[0], self.error[0])
    
    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)
