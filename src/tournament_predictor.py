from assassyn.frontend import *
from .debug_utils import debug_log


class TournamentPredictor(Module):
    """
    Architecture:
    - Bimodal: 2-bit saturating counters indexed by PC
    - Gshare: 2-bit counters indexed by (PC XOR Global History)
    - Selector: 2-bit counters that learn which predictor is better for each branch
    """

    def __init__(self, num_entries=64, index_bits=6, history_bits=6):
        """
        Initialize Tournament Predictor.

        Args:
            num_entries: Number of entries in each table (should be power of 2)
            index_bits: Number of bits for indexing (log2(num_entries))
            history_bits: Number of bits in global history register
        """
        super().__init__(ports={}, no_arbiter=True)
        self.name = "TournamentPredictor"
        self.num_entries = num_entries
        self.index_bits = index_bits
        self.history_bits = history_bits

    @module.combinational
    def build(self):
        # Bimodal predictor: 2-bit counters indexed by PC
        # Initialize to "Weakly Taken" (2) for better initial behavior on loops
        bimodal_counters = RegArray(
            Bits(2), self.num_entries, initializer=[2] * self.num_entries
        )

        # Gshare predictor: 2-bit counters indexed by (PC XOR Global History)
        # Initialize to "Weakly Taken" (2)
        gshare_counters = RegArray(
            Bits(2), self.num_entries, initializer=[2] * self.num_entries
        )

        # Global History Register (GHR): shift register of branch outcomes
        # Initialize to 0
        global_history = RegArray(Bits(self.history_bits), 1, initializer=[0])

        # Selector: 2-bit counters to choose between predictors
        # 00, 01: Use Bimodal
        # 10, 11: Use Gshare
        # Initialize to "Weakly Bimodal" (1) - slight preference for local predictor
        selector_counters = RegArray(
            Bits(2), self.num_entries, initializer=[1] * self.num_entries
        )

        return bimodal_counters, gshare_counters, global_history, selector_counters


class TournamentPredictorImpl:
    """
    Tournament Predictor implementation logic.
    Helper class with pure combinational logic methods.
    """

    def __init__(self, num_entries=64, index_bits=6, history_bits=6):
        self.name = "TournamentPredictor_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        self.history_bits = history_bits
        self.index_mask = (1 << index_bits) - 1

    def _get_pc_index(self, pc: Bits(32)):
        """Extract index from PC (skip lowest 2 bits for word alignment)."""
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        return index_32[0 : self.index_bits - 1].bitcast(Bits(self.index_bits))

    def _get_gshare_index(self, pc: Bits(32), global_history: Bits):
        """Calculate Gshare index: PC[index_bits:2] XOR Global History."""
        pc_bits = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        pc_index = pc_bits[0 : self.index_bits - 1].bitcast(Bits(self.index_bits))

        # XOR with global history (extend/truncate history to match index bits)
        ghr = global_history[0 : self.history_bits - 1].bitcast(Bits(self.history_bits))

        # Pad or truncate GHR to match index bits
        if self.history_bits >= self.index_bits:
            ghr_matched = ghr[0 : self.index_bits - 1].bitcast(Bits(self.index_bits))
        else:
            # Zero-extend GHR to index_bits
            ghr_matched = concat(
                Bits(self.index_bits - self.history_bits)(0), ghr
            ).bitcast(Bits(self.index_bits))

        return pc_index ^ ghr_matched

    def predict(
        self,
        pc: Bits(32),
        bimodal_counters: Array,
        gshare_counters: Array,
        global_history: Array,
        selector_counters: Array,
    ):
        """
        Predict branch direction using Tournament predictor.

        Returns:
            predict_taken: Bits(1) - 1 if predict taken, 0 if predict not-taken
        """
        # Get indices
        pc_index = self._get_pc_index(pc)
        ghr = global_history[0]
        gshare_index = self._get_gshare_index(pc, ghr)

        # Read predictor states
        bimodal_state = bimodal_counters[pc_index]
        gshare_state = gshare_counters[gshare_index]
        selector_state = selector_counters[pc_index]

        # Bimodal prediction: taken if counter >= 2
        bimodal_taken = bimodal_state[1:1]  # MSB indicates taken/not-taken

        # Gshare prediction: taken if counter >= 2
        gshare_taken = gshare_state[1:1]

        # Selector decision: use Gshare if selector >= 2, else use Bimodal
        use_gshare = selector_state[1:1]

        # Final prediction
        predict_taken = use_gshare.select(gshare_taken, bimodal_taken)

        # Debug logging
        with Condition(predict_taken == Bits(1)(1)):
            debug_log(
                "TP: PREDICT TAKEN at PC=0x{:x}, Bimodal={}, Gshare={}, Selector={}, UseGshare={}",
                pc,
                bimodal_state,
                gshare_state,
                selector_state,
                use_gshare,
            )
        with Condition(predict_taken == Bits(1)(0)):
            debug_log(
                "TP: PREDICT NOT-TAKEN at PC=0x{:x}, Bimodal={}, Gshare={}, Selector={}, UseGshare={}",
                pc,
                bimodal_state,
                gshare_state,
                selector_state,
                use_gshare,
            )

        return predict_taken

    def update(
        self,
        pc: Bits(32),
        actual_taken: Value,  # Bits(1): actual branch outcome
        is_branch: Value,  # Bits(1): whether this is a branch instruction
        bimodal_counters: Array,
        gshare_counters: Array,
        global_history: Array,
        selector_counters: Array,
    ):
        """
        Update Tournament predictor with actual branch outcome.

        Updates:
        1. Bimodal counter at PC index
        2. Gshare counter at (PC XOR GHR) index
        3. Selector counter based on which predictor was correct
        4. Global History Register
        """
        # Get indices
        pc_index = self._get_pc_index(pc)
        ghr = global_history[0]
        gshare_index = self._get_gshare_index(pc, ghr)

        with Condition(is_branch == Bits(1)(1)):
            # Read current counter states
            bimodal_state = bimodal_counters[pc_index]
            gshare_state = gshare_counters[gshare_index]
            selector_state = selector_counters[pc_index]

            # Determine what each predictor predicted
            bimodal_predicted_taken = bimodal_state[1:1]
            gshare_predicted_taken = gshare_state[1:1]

            # Check if each predictor was correct
            bimodal_correct = bimodal_predicted_taken == actual_taken
            gshare_correct = gshare_predicted_taken == actual_taken

            # --- Update Bimodal Counter ---
            # Increment if taken, decrement if not taken (saturating)
            bimodal_new = actual_taken.select(
                # Taken: increment (saturate at 3)
                (bimodal_state == Bits(2)(3)).select(
                    Bits(2)(3),
                    (bimodal_state.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2)),
                ),
                # Not Taken: decrement (saturate at 0)
                (bimodal_state == Bits(2)(0)).select(
                    Bits(2)(0),
                    (bimodal_state.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2)),
                ),
            )
            bimodal_counters[pc_index] <= bimodal_new

            # --- Update Gshare Counter ---
            gshare_new = actual_taken.select(
                # Taken: increment (saturate at 3)
                (gshare_state == Bits(2)(3)).select(
                    Bits(2)(3),
                    (gshare_state.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2)),
                ),
                # Not Taken: decrement (saturate at 0)
                (gshare_state == Bits(2)(0)).select(
                    Bits(2)(0),
                    (gshare_state.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2)),
                ),
            )
            gshare_counters[gshare_index] <= gshare_new

            # --- Update Selector Counter ---
            # Increment (toward Gshare) if Gshare correct and Bimodal wrong
            # Decrement (toward Bimodal) if Bimodal correct and Gshare wrong
            # No change if both correct or both wrong
            gshare_better = gshare_correct & (~bimodal_correct)
            bimodal_better = bimodal_correct & (~gshare_correct)

            selector_new = gshare_better.select(
                # Gshare was better: increment toward Gshare (saturate at 3)
                (selector_state == Bits(2)(3)).select(
                    Bits(2)(3),
                    (selector_state.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2)),
                ),
                bimodal_better.select(
                    # Bimodal was better: decrement toward Bimodal (saturate at 0)
                    (selector_state == Bits(2)(0)).select(
                        Bits(2)(0),
                        (selector_state.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2)),
                    ),
                    # Both correct or both wrong: no change
                    selector_state,
                ),
            )
            selector_counters[pc_index] <= selector_new

            # --- Update Global History Register ---
            # Shift left by 1 and insert new outcome
            ghr_shifted = (ghr << UInt(self.history_bits)(1)) | actual_taken.bitcast(
                Bits(self.history_bits)
            )
            # Keep only history_bits
            ghr_new = ghr_shifted[0 : self.history_bits - 1].bitcast(
                Bits(self.history_bits)
            )
            global_history[0] <= ghr_new

            debug_log(
                "TP: UPDATE at PC=0x{:x}, Taken={}, Bimodal: {}->{}, Gshare: {}->{}, Selector: {}->{}, GHR->{}",
                pc,
                actual_taken,
                bimodal_state,
                bimodal_new,
                gshare_state,
                gshare_new,
                selector_state,
                selector_new,
                ghr_new,
            )
