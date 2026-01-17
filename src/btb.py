from assassyn.frontend import *
from .debug_utils import debug_log


class BTB(Module):
    """
    Branch Target Buffer (BTB) implemented using SRAM.
    
    Each BTB entry contains:
    - valid (1 bit): whether the entry is valid
    - tag (32 bits): full PC stored as tag for exact matching
    - target (32 bits): branch target address
    
    Total: 65 bits per entry, stored in a 65-bit wide SRAM.
    
    Note: SRAM has 1-cycle read latency. The read is initiated in one cycle,
    and the result is available in the next cycle.
    """
    def __init__(self, num_entries=64, index_bits=6):
        """
        Initialize BTB with configurable size.

        Args:
            num_entries: Number of BTB entries (should be power of 2)
            index_bits: Number of bits to use for indexing (log2(num_entries))
        """
        super().__init__(ports={}, no_arbiter=True)
        self.name = "BTB"
        self.num_entries = num_entries
        self.index_bits = index_bits
        # Each entry contains: valid (1 bit) + tag (full 32-bit PC) + target (32 bits) = 65 bits

    @module.combinational
    def build(self):
        # BTB storage using SRAM
        # Width = 65 bits (1 valid + 32 tag + 32 target)
        # Depth = num_entries
        btb_sram = SRAM(width=65, depth=self.num_entries)
        btb_sram.name = "btb_sram"
        
        # Expose BTB SRAM for BTBImpl to use
        return btb_sram


class BTBImpl:
    """
    BTB implementation logic that interfaces with the BTB SRAM.
    
    The SRAM-based BTB uses a pipelined read approach:
    - drive_read(): Drive the SRAM read address (call in IF stage with current PC)
    - predict(): Read SRAM output and check for hit (call with previous PC for comparison)
    - update(): Drive the SRAM write (call in EX stage when branch is resolved)
    """
    def __init__(self, num_entries=64, index_bits=6):
        self.name = "BTB_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        # Mask for extracting index from PC
        self.index_mask = (1 << index_bits) - 1

    def _extract_index(self, pc):
        """Extract BTB index from PC (word-aligned, skip lowest 2 bits)."""
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        return index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

    def _pack_entry(self, valid, tag, target):
        """Pack BTB entry fields into a 65-bit value: [64]=valid, [63:32]=tag, [31:0]=target."""
        return concat(valid, tag, target)

    def _unpack_entry(self, entry):
        """Unpack 65-bit BTB entry into (valid, tag, target)."""
        valid = entry[64:64]
        tag = entry[32:63]
        target = entry[0:31]
        return valid, tag, target

    def drive_sram(
            self,
            read_pc: Bits(32),  # PC for read operation
            write_pc: Bits(32),  # PC for write operation
            write_target: Bits(32),  # Target address for write
            should_write: Value,  # Whether to perform write
            btb_sram: SRAM,  # BTB SRAM instance
    ):
        """
        Drive the BTB SRAM for both read and write operations.
        
        The SRAM is driven with:
        - Read: Always enabled, address from read_pc
        - Write: Conditional on should_write, address from write_pc
        
        Write has priority over read when both target the same address.
        """
        # Extract indices
        read_index = self._extract_index(read_pc)
        write_index = self._extract_index(write_pc)
        
        # Pack write data: valid=1, tag=write_pc, target=write_target
        write_data = self._pack_entry(Bits(1)(1), write_pc, write_target)
        
        # Determine SRAM address: write has priority
        sram_addr = should_write.select(
            write_index.bitcast(Bits(self.index_bits)),
            read_index.bitcast(Bits(self.index_bits))
        )
        
        # Drive SRAM
        btb_sram.build(
            addr=sram_addr,
            re=~should_write,  # Read when not writing
            we=should_write,
            wdata=write_data,
        )
        
        # Debug logging for write
        with Condition(should_write == Bits(1)(1)):
            debug_log("BTB: UPDATE at PC=0x{:x}, Index={}, Target=0x{:x}", write_pc, write_index, write_target)

    def predict(
            self,
            pc: Bits(32),  # PC to check against stored tag
            btb_sram: SRAM,  # BTB SRAM instance
    ):
        """
        Predict branch target using BTB SRAM output.
        
        Note: This reads from btb_sram.dout which has the data from the
        *previous* cycle's read address. The caller must ensure that the
        appropriate PC was used to drive the read in the previous cycle.
        
        Returns (hit, target) where hit indicates if prediction is valid.
        """
        # Read SRAM output (from previous cycle's read)
        entry = btb_sram.dout[0].bitcast(Bits(65))
        entry_valid, entry_tag, entry_target = self._unpack_entry(entry)
        
        # Check for hit: valid bit set AND PC matches
        tag_match = entry_tag == pc
        hit = entry_valid & tag_match

        # Debug logging
        with Condition(hit == Bits(1)(1)):
            debug_log("BTB: HIT at PC=0x{:x}, Target=0x{:x}", pc, entry_target)
        with Condition(hit == Bits(1)(0)):
            debug_log("BTB: MISS at PC=0x{:x}", pc)

        return hit, entry_target
