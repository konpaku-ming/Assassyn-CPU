"""
Assassyn-CPU: RISC-V 32-bit CPU implementation using Assassyn HDL

This package contains the implementation of a 5-stage pipelined CPU:
- fetch: Instruction Fetch (IF) stage
- decoder: Instruction Decode (ID) stage
- execution: Execute (EX) stage
- memory: Memory Access (MEM) stage
- writeback: Write Back (WB) stage
- data_hazard: Data hazard detection unit
- control_signals: Control signal definitions and constants
- instruction_table: RV32I instruction truth table
"""

__version__ = "0.1.0"
