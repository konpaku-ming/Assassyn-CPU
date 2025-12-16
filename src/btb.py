from assassyn.frontend import *


class BTB(Module):
    """
    Branch Target Buffer (BTB) - Direct-mapped, one-cycle prediction
    
    Provides fast branch target prediction by storing previously seen
    branch target addresses indexed by PC.
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
        # Each entry contains: valid (1 bit) + tag (full 32-bit PC) + target (32 bits)
        # We'll use separate arrays for simplicity
        
    @module.combinational
    def build(self):
        # BTB storage arrays
        # Valid bits for each entry
        btb_valid = RegArray(Bits(1), self.num_entries, initializer=[0] * self.num_entries)
        # Tag storage (upper bits of PC)
        btb_tags = RegArray(Bits(32), self.num_entries, initializer=[0] * self.num_entries)
        # Target address storage
        btb_targets = RegArray(Bits(32), self.num_entries, initializer=[0] * self.num_entries)
        
        # Expose BTB storage for BTBImpl to use
        return btb_valid, btb_tags, btb_targets


class BTBImpl(Downstream):
    """
    BTB Implementation logic for prediction and update.
    """
    
    def __init__(self, num_entries=64, index_bits=6):
        super().__init__()
        self.name = "BTB_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        # Mask for extracting index from PC
        self.index_mask = (1 << index_bits) - 1
        
    @downstream.combinational
    def predict(
        self,
        pc: Bits(32),  # Current PC to predict
        btb_valid: Array,  # BTB valid bits
        btb_tags: Array,  # BTB tags
        btb_targets: Array,  # BTB targets
    ):
        """
        Predict branch target for given PC.
        Returns (hit, target) where hit indicates if prediction is valid.
        """
        # Extract index from PC (word-aligned, so skip lowest 2 bits)
        # For 64 entries (6 index bits): bits [7:2] of PC
        index = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        
        # Look up BTB entry
        entry_valid = btb_valid[index]
        entry_tag = btb_tags[index]
        entry_target = btb_targets[index]
        
        # Check for hit: valid bit set AND PC matches (stored PC is full PC)
        # We compare full PCs to avoid bit manipulation issues
        tag_match = entry_tag == pc
        hit = entry_valid & tag_match
        
        # Debug logging
        with Condition(hit == Bits(1)(1)):
            log("BTB: HIT at PC=0x{:x}, Index={}, Target=0x{:x}", pc, index, entry_target)
        with Condition(hit == Bits(1)(0)):
            log("BTB: MISS at PC=0x{:x}, Index={}", pc, index)
        
        return hit, entry_target
        
    @downstream.combinational  
    def update(
        self,
        pc: Bits(32),  # Branch PC
        target: Bits(32),  # Branch target
        should_update: Value,  # Whether to update (branch taken)
        btb_valid: Array,  # BTB valid bits
        btb_tags: Array,  # BTB tags
        btb_targets: Array,  # BTB targets
    ):
        """
        Update BTB with resolved branch information.
        """
        # Extract index same as predict
        index = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        
        with Condition(should_update == Bits(1)(1)):
            log("BTB: UPDATE at PC=0x{:x}, Index={}, Target=0x{:x}", pc, index, target)
            # Update entry: store full PC as tag for exact comparison
            btb_valid[index] <= Bits(1)(1)
            btb_tags[index] <= pc
            btb_targets[index] <= target
