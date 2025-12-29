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


class TournamentPredictor(Module):
    """
    Tournament Predictor - Combines Local and Global predictors with a Chooser

    Architecture:
        1. Local Predictor: PC-indexed 2-bit saturating counters (like simple BHT)
        2. Global Predictor: GHR-indexed 2-bit saturating counters (Pattern History Table)
        3. Chooser: PC-indexed 2-bit counters that select between local and global

    Counter States (for all tables):
        00 (0): Strongly Not Taken / Strongly Local
        01 (1): Weakly Not Taken / Weakly Local
        10 (2): Weakly Taken / Weakly Global
        11 (3): Strongly Taken / Strongly Global

    This is designed to complete prediction in one cycle:
        - All table lookups happen in parallel
        - Chooser selects final prediction combinationally
    """

    def __init__(self, num_entries=64, index_bits=6, ghr_bits=6):
        """
        Initialize Tournament Predictor with configurable sizes.

        Args:
            num_entries: Number of entries in each table (should be power of 2)
            index_bits: Number of bits to use for PC indexing (log2(num_entries))
            ghr_bits: Number of bits in the Global History Register
        """
        super().__init__(ports={}, no_arbiter=True)
        self.name = "TournamentPredictor"
        self.num_entries = num_entries
        self.index_bits = index_bits
        self.ghr_bits = ghr_bits

    @module.combinational
    def build(self):
        # Local Predictor: PC-indexed 2-bit counters
        # Initialize to "Weakly Taken" (10 = 2)
        local_counters = RegArray(Bits(2), self.num_entries, initializer=[2] * self.num_entries)

        # Global History Register: shift register of recent branch outcomes
        # Initialize to 0 (no history)
        ghr = RegArray(Bits(self.ghr_bits), 1, initializer=[0])

        # Global Predictor: GHR-indexed 2-bit counters (Pattern History Table)
        # Initialize to "Weakly Taken" (10 = 2)
        global_counters = RegArray(Bits(2), self.num_entries, initializer=[2] * self.num_entries)

        # Chooser: PC-indexed 2-bit counters
        # 00/01 = prefer local, 10/11 = prefer global
        # Initialize to "Weakly Global" (10 = 2) - slightly prefer global initially
        chooser_counters = RegArray(Bits(2), self.num_entries, initializer=[2] * self.num_entries)

        return local_counters, ghr, global_counters, chooser_counters


class TournamentPredictorImpl:
    """
    Tournament Predictor Implementation logic for prediction and update.
    This is a helper class with pure combinational logic methods.

    Prediction (single cycle):
        1. Read local counter using PC index
        2. Read global counter using GHR
        3. Read chooser counter using PC index
        4. Select final prediction based on chooser MSB

    Update (on branch resolution):
        1. Update local counter based on actual outcome
        2. Update global counter based on actual outcome
        3. Update chooser if local and global disagreed
        4. Shift actual outcome into GHR
    """

    def __init__(self, num_entries=64, index_bits=6, ghr_bits=6):
        self.name = "TournamentPredictor_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        self.ghr_bits = ghr_bits
        self.index_mask = (1 << index_bits) - 1
        self.ghr_mask = (1 << ghr_bits) - 1

    def _get_pc_index(self, pc):
        """Extract index from PC (word-aligned, skip lowest 2 bits)."""
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        return index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

    def _saturating_increment(self, counter):
        """Increment 2-bit counter with saturation at 3."""
        counter_plus_1 = (counter.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2))
        is_max = counter == Bits(2)(3)
        return is_max.select(Bits(2)(3), counter_plus_1)

    def _saturating_decrement(self, counter):
        """Decrement 2-bit counter with saturation at 0."""
        counter_minus_1 = (counter.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2))
        is_min = counter == Bits(2)(0)
        return is_min.select(Bits(2)(0), counter_minus_1)

    def predict(
            self,
            pc: Bits(32),
            local_counters: Array,
            ghr: Array,
            global_counters: Array,
            chooser_counters: Array,
    ):
        """
        Make branch prediction using tournament logic.
        All lookups happen in parallel for single-cycle prediction.

        Returns: (predict_taken, local_pred, global_pred, chooser_val)
            - predict_taken: final prediction (1 = taken, 0 = not taken)
            - local_pred, global_pred, chooser_val: for logging/debugging
        """
        # Get PC index
        pc_index = self._get_pc_index(pc)

        # Get GHR value for global predictor indexing
        ghr_val = ghr[0]
        ghr_index = ghr_val[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

        # Parallel table lookups (all in same cycle)
        local_counter = local_counters[pc_index]
        global_counter = global_counters[ghr_index]
        chooser_counter = chooser_counters[pc_index]

        # Predictions from each predictor (MSB of 2-bit counter)
        local_pred = local_counter[1:1]  # 1 if counter >= 2
        global_pred = global_counter[1:1]  # 1 if counter >= 2

        # Chooser: MSB=0 -> use local, MSB=1 -> use global
        use_global = chooser_counter[1:1]

        # Final prediction
        predict_taken = use_global.select(global_pred, local_pred)

        # Debug logging
        with Condition(predict_taken == Bits(1)(1)):
            log("TOURNAMENT: PREDICT TAKEN at PC=0x{:x}, Local={}, Global={}, Chooser={}, UseGlobal={}",
                pc, local_pred, global_pred, chooser_counter, use_global)
        with Condition(predict_taken == Bits(1)(0)):
            log("TOURNAMENT: PREDICT NOT TAKEN at PC=0x{:x}, Local={}, Global={}, Chooser={}, UseGlobal={}",
                pc, local_pred, global_pred, chooser_counter, use_global)

        return predict_taken, local_pred, global_pred, use_global

    def update(
            self,
            pc: Bits(32),
            branch_taken: Value,  # Actual outcome (1 = taken, 0 = not taken)
            should_update: Value,  # Whether to update (is a conditional branch)
            local_counters: Array,
            ghr: Array,
            global_counters: Array,
            chooser_counters: Array,
    ):
        """
        Update tournament predictor tables based on actual branch outcome.
        Updates all tables in a single cycle.
        """
        # Get indices
        pc_index = self._get_pc_index(pc)
        ghr_val = ghr[0]
        ghr_index = ghr_val[0:self.index_bits - 1].bitcast(Bits(self.index_bits))

        # Get current counter values
        local_counter = local_counters[pc_index]
        global_counter = global_counters[ghr_index]
        chooser_counter = chooser_counters[pc_index]

        # Get predictions for chooser update
        local_pred = local_counter[1:1]
        global_pred = global_counter[1:1]

        # Update local counter
        new_local_taken = self._saturating_increment(local_counter)
        new_local_not_taken = self._saturating_decrement(local_counter)
        new_local = branch_taken.select(new_local_taken, new_local_not_taken)

        # Update global counter
        new_global_taken = self._saturating_increment(global_counter)
        new_global_not_taken = self._saturating_decrement(global_counter)
        new_global = branch_taken.select(new_global_taken, new_global_not_taken)

        # Update chooser only if local and global predictions differ
        # If global was correct and local was wrong: increment (toward global)
        # If local was correct and global was wrong: decrement (toward local)
        local_correct = local_pred == branch_taken
        global_correct = global_pred == branch_taken
        predictors_differ = local_pred != global_pred

        # Chooser update logic
        new_chooser_toward_global = self._saturating_increment(chooser_counter)
        new_chooser_toward_local = self._saturating_decrement(chooser_counter)

        # Only update chooser if predictions differed
        # global_correct & ~local_correct -> increment (prefer global more)
        # local_correct & ~global_correct -> decrement (prefer local more)
        chooser_increment = global_correct & ~local_correct
        chooser_decrement = local_correct & ~global_correct

        new_chooser = chooser_increment.select(
            new_chooser_toward_global,
            chooser_decrement.select(new_chooser_toward_local, chooser_counter)
        )

        # Update GHR: shift left and insert new outcome
        new_ghr = concat(ghr_val[0:self.ghr_bits - 2], branch_taken).bitcast(Bits(self.ghr_bits))

        with Condition(should_update == Bits(1)(1)):
            log("TOURNAMENT: UPDATE at PC=0x{:x}, Taken={}, LocalPred={}, GlobalPred={}, LocalCorrect={}, GlobalCorrect={}",
                pc, branch_taken, local_pred, global_pred, local_correct, global_correct)
            log("TOURNAMENT: Local {} -> {}, Global {} -> {}, Chooser {} -> {}, GHR {} -> {}",
                local_counter, new_local, global_counter, new_global,
                chooser_counter, new_chooser, ghr_val, new_ghr)

            # Write updated values
            local_counters[pc_index] <= new_local
            global_counters[ghr_index] <= new_global
            chooser_counters[pc_index] <= new_chooser
            ghr[0] <= new_ghr


# Keep BHT for backward compatibility (alias to simple local predictor behavior)
class BHT(Module):
    """
    Branch History Table (BHT) - 2-bit Saturating Counter Predictor
    
    DEPRECATED: Use TournamentPredictor instead.
    Kept for backward compatibility.
    """

    def __init__(self, num_entries=64, index_bits=6):
        super().__init__(ports={}, no_arbiter=True)
        self.name = "BHT"
        self.num_entries = num_entries
        self.index_bits = index_bits

    @module.combinational
    def build(self):
        bht_counters = RegArray(Bits(2), self.num_entries, initializer=[2] * self.num_entries)
        return bht_counters


class BHTImpl:
    """
    BHT Implementation - DEPRECATED, use TournamentPredictorImpl instead.
    Kept for backward compatibility.
    """

    def __init__(self, num_entries=64, index_bits=6):
        self.name = "BHT_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        self.index_mask = (1 << index_bits) - 1

    def predict(self, pc, bht_counters):
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        index = index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))
        counter = bht_counters[index]
        predict_taken = counter[1:1]
        return predict_taken

    def update(self, pc, branch_taken, should_update, bht_counters):
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        index = index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))
        current_counter = bht_counters[index]
        counter_plus_1 = (current_counter.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2))
        counter_minus_1 = (current_counter.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2))
        is_max = current_counter == Bits(2)(3)
        is_min = current_counter == Bits(2)(0)
        new_counter_taken = is_max.select(Bits(2)(3), counter_plus_1)
        new_counter_not_taken = is_min.select(Bits(2)(0), counter_minus_1)
        new_counter = branch_taken.select(new_counter_taken, new_counter_not_taken)
        with Condition(should_update == Bits(1)(1)):
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
