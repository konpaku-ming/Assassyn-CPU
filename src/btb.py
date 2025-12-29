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


class BHT(Module):
    """
    Branch History Table (BHT) - 2-bit Saturating Counter Predictor

    Provides branch direction prediction using 2-bit saturating counters.
    Used in conjunction with BTB for full branch prediction.

    Counter States:
        00 (0): Strongly Not Taken
        01 (1): Weakly Not Taken
        10 (2): Weakly Taken
        11 (3): Strongly Taken

    Prediction: Predict taken when counter >= 2 (MSB == 1)
    """

    def __init__(self, num_entries=64, index_bits=6):
        """
        Initialize BHT with configurable size.

        Args:
            num_entries: Number of BHT entries (should be power of 2)
            index_bits: Number of bits to use for indexing (log2(num_entries))
        """
        super().__init__(ports={}, no_arbiter=True)
        self.name = "BHT"
        self.num_entries = num_entries
        self.index_bits = index_bits

    @module.combinational
    def build(self):
        # BHT storage: 2-bit saturating counters
        # Initialize to "Weakly Taken" (10 = 2) for better initial prediction
        bht_counters = RegArray(Bits(2), self.num_entries, initializer=[2] * self.num_entries)

        # Expose BHT storage for BHTImpl to use
        return bht_counters


class BHTImpl:
    """
    BHT Implementation logic for prediction and update.
    This is a helper class with pure combinational logic methods,
    not a Downstream module, to avoid circular dependencies.
    """

    def __init__(self, num_entries=64, index_bits=6):
        self.name = "BHT_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        # Mask for extracting index from PC
        self.index_mask = (1 << index_bits) - 1

    def predict(
            self,
            pc: Bits(32),  # Current PC to predict
            bht_counters: Array,  # BHT counters
    ):
        """
        Predict branch direction for given PC.
        Returns predict_taken (1 if counter >= 2, i.e., MSB is 1).
        """
        # Extract index from PC (word-aligned, so skip lowest 2 bits)
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        # Cast to proper bit width for array indexing
        index = index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

        # Look up BHT entry
        counter = bht_counters[index]

        # Predict taken if counter >= 2 (MSB is 1)
        predict_taken = counter[1:1]

        # Debug logging
        with Condition(predict_taken == Bits(1)(1)):
            log("BHT: PREDICT TAKEN at PC=0x{:x}, Index={}, Counter={}", pc, index, counter)
        with Condition(predict_taken == Bits(1)(0)):
            log("BHT: PREDICT NOT TAKEN at PC=0x{:x}, Index={}, Counter={}", pc, index, counter)

        return predict_taken

    def update(
            self,
            pc: Bits(32),  # Branch PC
            branch_taken: Value,  # Actual branch outcome (1 = taken, 0 = not taken)
            should_update: Value,  # Whether to update (is a branch instruction)
            bht_counters: Array,  # BHT counters
    ):
        """
        Update BHT with resolved branch outcome using saturating counter logic.
        """
        # Extract index same as predict
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        # Cast to proper bit width for array indexing
        index = index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

        # Get current counter value
        current_counter = bht_counters[index]

        # Saturating counter update logic:
        # If taken: increment (saturate at 3)
        # If not taken: decrement (saturate at 0)
        counter_plus_1 = (current_counter.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2))
        counter_minus_1 = (current_counter.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2))

        # Saturate at boundaries
        is_max = current_counter == Bits(2)(3)  # Already at max (11)
        is_min = current_counter == Bits(2)(0)  # Already at min (00)

        # New counter value based on branch outcome
        new_counter_taken = is_max.select(Bits(2)(3), counter_plus_1)
        new_counter_not_taken = is_min.select(Bits(2)(0), counter_minus_1)
        new_counter = branch_taken.select(new_counter_taken, new_counter_not_taken)

        with Condition(should_update == Bits(1)(1)):
            log("BHT: UPDATE at PC=0x{:x}, Index={}, Old={}, New={}, Taken={}",
                pc, index, current_counter, new_counter, branch_taken)
            bht_counters[index] <= new_counter


class BTBImpl:
    """
    BTB Implementation logic for prediction and update.
    This is a helper class with pure combinational logic methods,
    not a Downstream module, to avoid circular dependencies.
    """

    def __init__(self, num_entries=64, index_bits=6):
        self.name = "BTB_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        # Mask for extracting index from PC
        self.index_mask = (1 << index_bits) - 1

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
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        # Cast to proper bit width for array indexing
        index = index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

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
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        # Cast to proper bit width for array indexing
        index = index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

        with Condition(should_update == Bits(1)(1)):
            log("BTB: UPDATE at PC=0x{:x}, Index={}, Target=0x{:x}", pc, index, target)
            # Update entry: store full PC as tag for exact comparison
            btb_valid[index] <= Bits(1)(1)
            btb_tags[index] <= pc
            btb_targets[index] <= target
